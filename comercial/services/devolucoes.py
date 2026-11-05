# comercial/services/devolucoes.py
#
# Devoluções. Venda: o cliente devolve parte (ou tudo) do que comprou. Compra: mais abaixo.
#   - Estoque: o produto volta pelo custo com que saiu na venda (o do CMV). Sem condição de revenda,
#     entra e sai na hora como perda.
#   - Financeiro: o valor devolvido abate primeiro as parcelas em aberto da venda (das últimas para as
#     primeiras); o que o cliente já tinha pago vira reembolso no caixa ou crédito do cliente (conta a pagar).
#   - DRE e Painel leem as devoluções confirmadas pela data da devolução (relatorios/services).
# A venda continua como estava: o estorno (cancelar a venda inteira) é para erro de lançamento.
import re
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.formats import number_format

from comercial.models import (CMVItem, Compra, Devolucao, DevolucaoItem, DevolucaoTitulo, Estoque, MovimentacaoEstoque,
                               Venda)
from financeiro.models import CaixaMovimento, FinanceiroCategoria, FinanceiroPagar, FinanceiroReceber
from financeiro.services import FinanceiroErro, caixa_principal, titulo_pago

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")
# Prazos que geram aviso (não bloqueiam): 7 dias do CDC, 30 e 90 dias
PRAZOS_AVISO = (90, 30, 7)


def reais(valor):
    return number_format(valor, 2, force_grouping=True)


class DevolucaoErro(Exception):
    """Devolução recusada; a mensagem é mostrada ao usuário."""


def _titulos_da_venda(venda):
    return FinanceiroReceber.objects.filter(
        origem="VENDA", content_type=ContentType.objects.get_for_model(Venda), object_id=venda.id)


def venda_tem_devolucao(venda):
    return venda.devolucoes.filter(status="confirmada").exists()


def total_devolvido(venda):
    return venda.devolucoes.filter(status="confirmada").aggregate(t=Sum("valor_total"))["t"] or ZERO


# Itens da venda com o que ainda pode ser devolvido, o valor líquido unitário e o custo do CMV.
# O desconto e o acréscimo dados na venda inteira são rateados pelos itens.
def itens_devolviveis(venda):
    total_itens = venda.total_itens
    fator = (venda.total / total_itens) if total_itens else Decimal("0")
    custos = dict(CMVItem.objects.filter(venda=venda).values_list("item_id", "custo_medio"))
    devolvido = dict(
        DevolucaoItem.objects.filter(venda_item__venda=venda, devolucao__status="confirmada")
        .values("venda_item").annotate(q=Sum("quantidade")).values_list("venda_item", "q")
    )
    linhas = []
    for item in venda.itens.select_related("produto", "servico").order_by("id"):
        ja = devolvido.get(item.id) or Decimal("0")
        linhas.append({
            "item": item,
            "vendido": item.quantidade,
            "devolvido": ja,
            "disponivel": item.quantidade - ja,
            "valor_liquido": item.total * fator,  # do item inteiro
            "valor_unitario": (item.total * fator / item.quantidade).quantize(CENTAVO) if item.quantidade else ZERO,
            "custo": (custos.get(item.id, item.custo_medio) or ZERO) if item.produto_id else ZERO,
        })
    return linhas


def dias_desde_venda(venda, data):
    return (data - timezone.localdate(venda.data_emissao)).days


def aviso_prazo(venda, data):
    dias = dias_desde_venda(venda, data)
    for prazo in PRAZOS_AVISO:
        if dias > prazo:
            return f"A venda foi há {dias} dias (mais de {prazo}). Confira se a devolução ainda é aceita."
    return ""


# Monta a devolução sem gravar nada, para a tela mostrar o impacto antes de confirmar.
# pedidos: {id do item da venda: (quantidade, volta_estoque)}
def planejar_devolucao_venda(venda, pedidos):
    if venda.status != "finalizada":
        raise DevolucaoErro("Só vendas finalizadas podem ter devolução.")

    linhas = itens_devolviveis(venda)
    itens = []
    for linha in linhas:
        qtd, volta = pedidos.get(linha["item"].id, (Decimal("0"), True))
        if not qtd:
            continue
        if qtd < 0:
            raise DevolucaoErro(f"Quantidade inválida para {linha['item']}.")
        if qtd > linha["disponivel"]:
            raise DevolucaoErro(
                f"{linha['item'].produto or linha['item'].servico}: só restam {linha['disponivel']:g} para devolver.")
        itens.append({
            "linha": linha,
            "item": linha["item"],
            "quantidade": qtd,
            "valor": (linha["valor_liquido"] * qtd / linha["vendido"]).quantize(CENTAVO),
            "custo": linha["custo"],
            "custo_total": (linha["custo"] * qtd).quantize(CENTAVO),
            "volta_estoque": bool(volta) if linha["item"].produto_id else False,
            "produto": linha["item"].produto_id is not None,
        })
    if not itens:
        raise DevolucaoErro("Informe a quantidade devolvida de pelo menos um item.")

    ja_devolvido = total_devolvido(venda)
    valor_total = sum((i["valor"] for i in itens), ZERO)
    # Venda devolvida por inteiro: o total fecha com o da venda (sem sobrar centavo do rateio)
    tudo = all(l["disponivel"] == next((i["quantidade"] for i in itens if i["item"].id == l["item"].id), 0)
               for l in linhas)
    if tudo or ja_devolvido + valor_total > venda.total:
        ajuste = (venda.total - ja_devolvido) - valor_total
        if tudo or ajuste < 0:
            itens[-1]["valor"] += ajuste
            valor_total += ajuste

    # Abate das parcelas em aberto, da última para a primeira
    abatimentos, restante = [], valor_total
    for titulo in _titulos_da_venda(venda).filter(status="pendente").order_by("-data_vencimento", "-id"):
        if restante <= 0:
            break
        valor = min(titulo.valor, restante)
        abatimentos.append({"titulo": titulo, "valor": valor, "cancela": valor == titulo.valor})
        restante -= valor

    return {
        "itens": itens,
        "valor_total": valor_total,
        "valor_custo": sum((i["custo_total"] for i in itens if i["produto"]), ZERO),
        "abatimentos": abatimentos,
        "valor_abatido": valor_total - restante,
        "restante": restante,
    }


def _nota(texto, usuario):
    return f"{timezone.localtime():%d/%m/%Y %H:%M} {usuario or 'usuário'}: {texto}"


# Grava a devolução planejada. dados: data, motivo, observacao, acerto, nf_numero, nf_chave, xml_nfe, posvenda
def registrar_devolucao_venda(venda, pedidos, dados, usuario=None):
    with transaction.atomic():
        # Trava a venda: duas devoluções ao mesmo tempo não passam do que foi vendido
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        plano = planejar_devolucao_venda(venda, pedidos)
        acerto = dados.get("acerto") or ""
        if plano["restante"] > 0 and acerto not in ("reembolso", "credito"):
            raise DevolucaoErro(
                f"O cliente já pagou R$ {reais(plano['restante'])} desta devolução: escolha reembolso ou crédito.")
        if plano["restante"] <= 0:
            acerto = ""

        dev = Devolucao.objects.create(
            tipo="VENDA", venda=venda, contato=venda.cliente,
            data=dados.get("data") or timezone.localdate(),
            motivo=dados.get("motivo") or "outro",
            observacao=dados.get("observacao") or "",
            acerto=acerto,
            valor_total=plano["valor_total"],
            valor_custo=plano["valor_custo"],
            valor_abatido=plano["valor_abatido"],
            nf_numero=dados.get("nf_numero") or "",
            nf_chave=dados.get("nf_chave") or "",
            xml_nfe=dados.get("xml_nfe") or "",
            posvenda=dados.get("posvenda"),
            usuario=usuario if getattr(usuario, "pk", None) else None,
        )

        # Itens e estoque
        for i in plano["itens"]:
            item = i["item"]
            DevolucaoItem.objects.create(
                devolucao=dev, venda_item=item, produto=item.produto, servico=item.servico,
                quantidade=i["quantidade"], valor_total=i["valor"], custo_unitario=i["custo"],
                volta_estoque=i["volta_estoque"],
            )
            if not item.produto_id:
                continue  # serviço não tem estoque
            # Venda antiga sem custo: devolve a quantidade sem mexer no preço médio
            _entrada(item.produto, i["quantidade"], i["custo"], "DEVOLUCAO_VENDA", dev.id)
            if not i["volta_estoque"]:
                MovimentacaoEstoque.objects.create(
                    produto=item.produto, tipo="SAIDA", quantidade=i["quantidade"],
                    origem="PERDA_DEVOLUCAO", referencia_id=dev.id)

        # Parcelas em aberto
        for ab in plano["abatimentos"]:
            titulo = FinanceiroReceber.objects.select_for_update().get(pk=ab["titulo"].pk)
            if titulo.status != "pendente" or titulo_pago(titulo):
                raise DevolucaoErro(f"A parcela \"{titulo.descricao}\" mudou enquanto a devolução era registrada.")
            if ab["cancela"]:
                titulo.status = "cancelado"
                texto = f"cancelado pela devolução #{dev.id} (R$ {reais(ab['valor'])})"
            else:
                titulo.valor -= ab["valor"]
                texto = f"valor reduzido em R$ {reais(ab['valor'])} pela devolução #{dev.id}"
            titulo.observacao = f"{titulo.observacao}\n{_nota(texto, usuario)}".strip()
            titulo.save()
            DevolucaoTitulo.objects.create(devolucao=dev, receber=titulo, valor_abatido=ab["valor"], cancelou=ab["cancela"])

        # O que o cliente já tinha pago
        restante = plano["restante"]
        if restante > 0 and acerto == "reembolso":
            try:
                caixa = caixa_principal()
            except FinanceiroErro as erro:
                raise DevolucaoErro(str(erro))
            if caixa.saldo_atual() < restante:
                raise DevolucaoErro("Saldo insuficiente no caixa para o reembolso. Escolha crédito do cliente.")
            CaixaMovimento.objects.create(
                caixa=caixa, data=dev.data, valor=restante, tipo="S", origem="DEVOLUCAO",
                descricao=f"Reembolso da devolução #{dev.id} (venda {venda.numero_formatado})",
                referencia_id=dev.id)
            dev.valor_reembolso = restante
        elif restante > 0:
            categoria, _ = FinanceiroCategoria.objects.get_or_create(nome="Devoluções de vendas", defaults={"tipo": "D"})
            credito = FinanceiroPagar.objects.create(
                data_lancamento=dev.data, data_vencimento=dev.data, contato=venda.cliente,
                descricao=f"Crédito da devolução #{dev.id} (venda {venda.numero_formatado})",
                valor=restante, categoria=categoria, origem="DEVOLUCAO",
                content_type=ContentType.objects.get_for_model(Devolucao), object_id=dev.id)
            DevolucaoTitulo.objects.create(devolucao=dev, pagar=credito, gerado=True)
            dev.valor_credito = restante
        dev.save()

    cache.clear()  # o Painel guarda os números por 5 minutos
    return dev


# Desfaz a devolução (de venda ou de compra): o estoque volta ao que era, as parcelas voltam ao
# valor anterior, o reembolso é estornado no caixa e o crédito é cancelado. Recusa se algo já foi
# usado depois (parcela abatida quitada, crédito pago).
def cancelar_devolucao(dev, usuario=None, motivo=""):
    with transaction.atomic():
        dev = Devolucao.objects.select_for_update().get(pk=dev.pk)
        if dev.status != "confirmada":
            raise DevolucaoErro("Esta devolução já foi cancelada.")
        venda = dev.tipo == "VENDA"

        vinculos = list(dev.titulos.select_related("receber", "pagar"))
        for v in vinculos:
            titulo = v.receber or v.pagar
            if v.gerado:
                if titulo_pago(titulo):
                    raise DevolucaoErro("O crédito desta devolução já foi quitado. Estorne a quitação antes de cancelar.")
            elif titulo.status != ("cancelado" if v.cancelou else "pendente") or titulo_pago(titulo):
                raise DevolucaoErro(
                    f"A parcela \"{titulo.descricao}\" foi alterada ou quitada depois da devolução. "
                    "Estorne a quitação antes de cancelar.")

        if venda:
            # Só os itens que voltaram para a prateleira saem de novo (a perda já entrou e saiu)
            for item in dev.itens.filter(produto__isnull=False, volta_estoque=True).select_related("produto"):
                try:
                    MovimentacaoEstoque.objects.create(
                        produto=item.produto, tipo="SAIDA", quantidade=item.quantidade,
                        origem="DEVOLUCAO_CANCELADA", referencia_id=dev.id)
                except ValueError:
                    raise DevolucaoErro(f"{item.produto}: o estoque não tem mais a quantidade devolvida para tirar de novo.")
        else:
            # A mercadoria volta pelo mesmo custo com que saiu: o preço médio volta ao que era
            for item in dev.itens.filter(produto__isnull=False).select_related("produto"):
                _entrada(item.produto, item.quantidade, item.custo_unitario, "DEVOLUCAO_COMPRA_CANCELADA", dev.id)

        texto = f"devolução #{dev.id} cancelada"
        for v in vinculos:
            titulo = v.receber or v.pagar
            if v.gerado:
                titulo.status = "cancelado"
            elif v.cancelou:
                titulo.status = "pendente"
            else:
                titulo.valor += v.valor_abatido
            titulo.observacao = f"{titulo.observacao}\n{_nota(texto, usuario)}".strip()
            titulo.save()

        if dev.valor_reembolso > 0:
            # Venda: o reembolso saiu do caixa e volta; compra: o fornecedor devolveu e o valor sai
            original = CaixaMovimento.objects.filter(origem="DEVOLUCAO", referencia_id=dev.id).first()
            CaixaMovimento.objects.create(
                caixa=original.caixa if original and original.caixa else caixa_principal(),
                data=timezone.localdate(), valor=dev.valor_reembolso, tipo="E" if venda else "S", origem="ESTORNO",
                descricao=f"Estorno do reembolso da devolução #{dev.id}", referencia_id=dev.id)

        dev.status = "cancelada"
        dev.cancelada_em = timezone.now()
        dev.motivo_cancelamento = motivo or ""
        dev.save()

    cache.clear()
    return dev


def _entrada(produto, quantidade, custo, origem, referencia_id):
    if custo > 0:
        MovimentacaoEstoque.objects.create(produto=produto, tipo="ENTRADA", quantidade=quantidade, preco=custo,
                                           origem=origem, referencia_id=referencia_id)
    else:
        # Sem custo: devolve a quantidade sem mexer no preço médio
        MovimentacaoEstoque.objects.create(produto=produto, tipo="ENTRADA", quantidade=quantidade,
                                           origem=f"ESTORNO_{origem}", referencia_id=referencia_id)


#====================================
# DEVOLUÇÃO DE COMPRA (devolvemos ao fornecedor)
#====================================
# Estoque: a mercadoria sai pelo custo com que entrou e o preço médio é recalculado como se aquela
# entrada não tivesse existido. Financeiro: abate as duplicatas em aberto da compra; o que já foi pago
# vira reembolso (entrada no caixa) ou crédito com o fornecedor (conta a receber). Não entra no DRE:
# a compra também não entra (vira estoque).

def compra_tem_devolucao(compra):
    return compra.devolucoes.filter(status="confirmada").exists()


def _titulos_da_compra(compra):
    return FinanceiroPagar.objects.filter(compra=compra, origem="COMPRA")


# Itens da compra com o que ainda pode ser devolvido. A quantidade é a da nota (unidade do fornecedor);
# no estoque entra multiplicada pelo fator de conversão do item.
def itens_devolviveis_compra(compra):
    devolvido = dict(
        DevolucaoItem.objects.filter(compra_item__compra=compra, devolucao__status="confirmada")
        .values("compra_item").annotate(q=Sum("quantidade")).values_list("compra_item", "q")
    )
    saldos = dict(Estoque.objects.filter(produto__in=compra.itens.values("produto")).values_list("produto_id", "quantidade"))
    linhas = []
    for item in compra.itens.select_related("produto").order_by("id"):
        if not item.produto_id:
            continue  # item sem vínculo não entrou no estoque
        fator = Decimal(item.fator_conversao or 1)
        ja = (devolvido.get(item.id) or Decimal("0")) / fator  # gravado em unidade de estoque
        linhas.append({
            "item": item,
            "fator": fator,
            "vendido": item.quantidade,  # comprado; mesmo nome da venda para a tela
            "devolvido": ja,
            "disponivel": Decimal(item.quantidade) - ja,
            "valor_liquido": item.valor_nota,
            "valor_unitario": (item.valor_nota / item.quantidade).quantize(CENTAVO) if item.quantidade else ZERO,
            "custo": item.custo_unitario_estoque.quantize(CENTAVO),
            "saldo": saldos.get(item.produto_id) or Decimal("0"),
        })
    return linhas


def total_devolvido_compra(compra):
    return compra.devolucoes.filter(status="confirmada").aggregate(t=Sum("valor_total"))["t"] or ZERO


# pedidos: {id do item da compra: quantidade na unidade da nota}
def planejar_devolucao_compra(compra, pedidos):
    if not compra.confirmada:
        raise DevolucaoErro("Só compras confirmadas podem ter devolução.")

    linhas = itens_devolviveis_compra(compra)
    itens = []
    for linha in linhas:
        qtd = pedidos.get(linha["item"].id) or Decimal("0")
        if not qtd:
            continue
        if qtd < 0:
            raise DevolucaoErro(f"Quantidade inválida para {linha['item'].descricao}.")
        if qtd > linha["disponivel"]:
            raise DevolucaoErro(f"{linha['item'].descricao}: só restam {linha['disponivel']:g} para devolver.")
        qtd_estoque = qtd * linha["fator"]
        if qtd_estoque > linha["saldo"]:
            raise DevolucaoErro(
                f"{linha['item'].produto}: o estoque tem {linha['saldo']:g} e a devolução tira {qtd_estoque:g}.")
        itens.append({
            "linha": linha,
            "item": linha["item"],
            "quantidade": qtd,
            "quantidade_estoque": qtd_estoque,
            "valor": (linha["valor_liquido"] * qtd / linha["vendido"]).quantize(CENTAVO),
            "custo": linha["custo"],
            "custo_total": (linha["custo"] * qtd_estoque).quantize(CENTAVO),
            "produto": True,
            "volta_estoque": False,
        })
    if not itens:
        raise DevolucaoErro("Informe a quantidade devolvida de pelo menos um item.")

    ja_devolvido = total_devolvido_compra(compra)
    valor_total = sum((i["valor"] for i in itens), ZERO)
    tudo = all(l["disponivel"] == next((i["quantidade"] for i in itens if i["item"].id == l["item"].id), 0)
               for l in linhas)
    if tudo or ja_devolvido + valor_total > compra.valor_total:
        ajuste = (compra.valor_total - ja_devolvido) - valor_total
        if tudo or ajuste < 0:
            itens[-1]["valor"] += ajuste
            valor_total += ajuste

    abatimentos, restante = [], valor_total
    for titulo in _titulos_da_compra(compra).filter(status="pendente").order_by("-data_vencimento", "-id"):
        if restante <= 0:
            break
        if titulo_pago(titulo):
            continue
        valor = min(titulo.valor, restante)
        abatimentos.append({"titulo": titulo, "valor": valor, "cancela": valor == titulo.valor})
        restante -= valor

    return {
        "itens": itens,
        "valor_total": valor_total,
        "valor_custo": sum((i["custo_total"] for i in itens), ZERO),
        "abatimentos": abatimentos,
        "valor_abatido": valor_total - restante,
        "restante": restante,
    }


def registrar_devolucao_compra(compra, pedidos, dados, usuario=None):
    with transaction.atomic():
        compra = Compra.objects.select_for_update().get(pk=compra.pk)
        plano = planejar_devolucao_compra(compra, pedidos)
        acerto = dados.get("acerto") or ""
        if plano["restante"] > 0 and acerto not in ("reembolso", "credito"):
            raise DevolucaoErro(
                f"A compra já foi paga em R$ {reais(plano['restante'])} deste valor: escolha reembolso ou crédito.")
        if plano["restante"] <= 0:
            acerto = ""

        dev = Devolucao.objects.create(
            tipo="COMPRA", compra=compra, contato=compra.fornecedor,
            data=dados.get("data") or timezone.localdate(),
            motivo=dados.get("motivo") or "outro",
            observacao=dados.get("observacao") or "",
            acerto=acerto,
            valor_total=plano["valor_total"],
            valor_custo=plano["valor_custo"],
            valor_abatido=plano["valor_abatido"],
            nf_numero=dados.get("nf_numero") or "",
            nf_chave=dados.get("nf_chave") or "",
            xml_nfe=dados.get("xml_nfe") or "",
            usuario=usuario if getattr(usuario, "pk", None) else None,
        )

        for i in plano["itens"]:
            item = i["item"]
            DevolucaoItem.objects.create(
                devolucao=dev, compra_item=item, produto=item.produto,
                quantidade=i["quantidade_estoque"], valor_total=i["valor"], custo_unitario=i["custo"],
                volta_estoque=False,
            )
            MovimentacaoEstoque.objects.create(
                produto=item.produto, tipo="SAIDA", quantidade=i["quantidade_estoque"], preco=i["custo"],
                origem="DEVOLUCAO_COMPRA", referencia_id=dev.id)

        for ab in plano["abatimentos"]:
            titulo = FinanceiroPagar.objects.select_for_update().get(pk=ab["titulo"].pk)
            if titulo.status != "pendente" or titulo_pago(titulo):
                raise DevolucaoErro(f"A duplicata \"{titulo.descricao}\" mudou enquanto a devolução era registrada.")
            if ab["cancela"]:
                titulo.status = "cancelado"
                texto = f"cancelado pela devolução #{dev.id} (R$ {reais(ab['valor'])})"
            else:
                titulo.valor -= ab["valor"]
                texto = f"valor reduzido em R$ {reais(ab['valor'])} pela devolução #{dev.id}"
            titulo.observacao = f"{titulo.observacao}\n{_nota(texto, usuario)}".strip()
            titulo.save()
            DevolucaoTitulo.objects.create(devolucao=dev, pagar=titulo, valor_abatido=ab["valor"], cancelou=ab["cancela"])

        restante = plano["restante"]
        if restante > 0 and acerto == "reembolso":
            try:
                caixa = caixa_principal()
            except FinanceiroErro as erro:
                raise DevolucaoErro(str(erro))
            CaixaMovimento.objects.create(
                caixa=caixa, data=dev.data, valor=restante, tipo="E", origem="DEVOLUCAO",
                descricao=f"Reembolso do fornecedor: devolução #{dev.id} (compra nota {compra.numero_formatado})",
                referencia_id=dev.id)
            dev.valor_reembolso = restante
        elif restante > 0:
            categoria, _ = FinanceiroCategoria.objects.get_or_create(nome="Devoluções de compras", defaults={"tipo": "R"})
            credito = FinanceiroReceber.objects.create(
                data_lancamento=dev.data, data_vencimento=dev.data, cliente=compra.fornecedor,
                descricao=f"Crédito com fornecedor: devolução #{dev.id} (compra nota {compra.numero_formatado})",
                valor=restante, categoria=categoria, origem="DEVOLUCAO",
                content_type=ContentType.objects.get_for_model(Devolucao), object_id=dev.id)
            DevolucaoTitulo.objects.create(devolucao=dev, receber=credito, gerado=True)
            dev.valor_credito = restante
        dev.save()

    cache.clear()
    return dev


# Chave e número da NF-e a partir do XML enviado (só leitura; a nota é emitida fora do sistema)
def dados_do_xml(xml):
    chave = re.search(r"<chNFe>(\d{44})</chNFe>", xml) or re.search(r'Id="NFe(\d{44})"', xml)
    numero = re.search(r"<nNF>(\d+)</nNF>", xml)
    return (chave.group(1) if chave else ""), (numero.group(1) if numero else "")
