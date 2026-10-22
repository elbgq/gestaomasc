# Regras do fluxo financeiro usadas por todas as telas:
# quitação e estorno de títulos, caixa padrão e saldo geral.
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from django.contrib.contenttypes.models import ContentType

from financeiro.models import (
    Caixa, CaixaMovimento, FinanceiroCategoria, FinanceiroLancamento, FinanceiroPagar, FinanceiroReceber
)


class FinanceiroErro(Exception):
    """Operação recusada; a mensagem é mostrada ao usuário."""


def caixa_principal():
    caixa = Caixa.objects.filter(nome="Caixa Principal").first()
    if caixa is None:
        raise FinanceiroErro('Cadastre o caixa "Caixa Principal" antes de movimentar o financeiro.')
    return caixa


# Saldo de todo o dinheiro da empresa: soma dos caixas ativos (saldo inicial + movimentos)
def saldo_geral():
    return sum((c.saldo_atual() for c in Caixa.objects.filter(ativo=True)), Decimal("0.00"))


def titulo_pago(titulo):
    return titulo.status == "pago" or bool(titulo.esta_pago())


CENTAVO = Decimal("0.01")


# Quita um título a pagar ou a receber e lança o movimento no caixa.
# valor: quanto do título está sendo quitado (padrão: tudo). Se for menor, o título é dividido:
#   a parte quitada fica neste título e o restante vira um título novo em aberto, "(saldo)".
# juros, multa e desconto entram no movimento de caixa e ficam gravados no título.
def quitar_titulo(titulo, data=None, valor=None, juros=0, multa=0, desconto=0):
    data = data or timezone.localdate()
    pagar = isinstance(titulo, FinanceiroPagar)
    juros, multa, desconto = (Decimal(str(v or 0)).quantize(CENTAVO) for v in (juros, multa, desconto))

    with transaction.atomic():
        titulo = type(titulo).objects.select_for_update().get(pk=titulo.pk)

        if titulo_pago(titulo):
            raise FinanceiroErro("Este título já foi quitado.")
        if titulo.status == "cancelado":
            raise FinanceiroErro("Título cancelado não pode ser quitado.")

        principal = titulo.valor if valor is None else Decimal(str(valor)).quantize(CENTAVO)
        if principal <= 0 or principal > titulo.valor:
            raise FinanceiroErro(f"O valor a quitar deve ser maior que zero e no máximo R$ {titulo.valor:.2f}.")
        if min(juros, multa, desconto) < 0:
            raise FinanceiroErro("Juros, multa e desconto não podem ser negativos.")
        total = principal + juros + multa - desconto
        if total <= 0:
            raise FinanceiroErro("O desconto não pode ser maior que o valor quitado.")

        caixa = caixa_principal()
        if pagar and caixa.saldo_atual() < total:
            raise FinanceiroErro("Saldo insuficiente no caixa para quitar este título.")

        # Pagamento parcial: o restante vira um título novo, com o mesmo vencimento
        restante = titulo.valor - principal
        if restante > 0:
            saldo = type(titulo).objects.get(pk=titulo.pk)
            saldo.pk = None
            saldo.valor = restante
            if not titulo.descricao.endswith("(saldo)"):
                saldo.descricao = f"{titulo.descricao} (saldo)"[:200]
            saldo.save()
            titulo.valor = principal

        mov = CaixaMovimento.objects.create(
            caixa=caixa,
            data=data,
            descricao=f"{'Pagamento' if pagar else 'Recebimento'}: {titulo.descricao}",
            valor=total,
            tipo="S" if pagar else "E",
            origem="PAGAMENTO" if pagar else "RECEITA",
            referencia_id=titulo.id,
            referencia_tipo="D" if pagar else "R",
            observacao=detalhe_acrescimos(principal, juros, multa, desconto),
        )

        titulo.status = "pago"
        titulo.valor_pago = principal
        titulo.valor_juros, titulo.valor_multa, titulo.valor_desconto = juros, multa, desconto
        titulo.data_pagamento = data
        titulo.caixa_movimento = mov
        titulo.save()

    return mov


def detalhe_acrescimos(principal, juros, multa, desconto):
    if not (juros or multa or desconto):
        return None
    partes = [f"Título R$ {principal:.2f}"]
    partes += [f"{nome} R$ {v:.2f}" for nome, v in (("juros", juros), ("multa", multa), ("desconto", desconto)) if v]
    return ", ".join(partes)


# Desfaz a quitação: lança o movimento inverso no caixa e volta o título para pendente.
# O movimento original fica no histórico.
def estornar_quitacao(titulo, data=None):
    data = data or timezone.localdate()
    pagar = isinstance(titulo, FinanceiroPagar)

    with transaction.atomic():
        titulo = type(titulo).objects.select_for_update().get(pk=titulo.pk)

        if not titulo_pago(titulo):
            raise FinanceiroErro("Este título não está quitado.")

        original = titulo.caixa_movimento
        valor = original.valor if original else titulo.total_quitado()

        mov = CaixaMovimento.objects.create(
            caixa=original.caixa if original and original.caixa else caixa_principal(),
            data=data,
            descricao=f"Estorno da quitação: {titulo.descricao}",
            valor=valor,
            tipo="E" if pagar else "S",
            origem="ESTORNO",
            referencia_id=titulo.id,
            referencia_tipo="D" if pagar else "R",
        )

        titulo.status = "pendente"
        titulo.valor_pago = None if pagar else Decimal("0.00")
        titulo.valor_juros = titulo.valor_multa = titulo.valor_desconto = Decimal("0.00")
        titulo.data_pagamento = None
        titulo.caixa_movimento = None
        titulo.save()

    return mov


def buscar_titulo(tipo, pk):
    modelo = {"D": FinanceiroPagar, "R": FinanceiroReceber}.get(tipo)
    if modelo is None:
        return None
    return modelo.objects.filter(pk=pk).first()


# Categoria sugerida para um contato: a padrão do cadastro ou, se não houver,
# a última usada com ele num lançamento ou numa conta manual. tipo: "D", "R" ou None (qualquer).
def categoria_sugerida(contato, tipo=None):
    def do_tipo(categoria):
        return categoria if categoria and (tipo is None or categoria.tipo == tipo) else None

    if do_tipo(contato.categoria_padrao):
        return contato.categoria_padrao, "padrao"

    usadas = []
    for qs in (
        FinanceiroLancamento.objects.filter(contato=contato),
        FinanceiroPagar.objects.filter(contato=contato, origem="MANUAL"),
        FinanceiroReceber.objects.filter(cliente=contato, origem="MANUAL"),
    ):
        if tipo:
            qs = qs.filter(categoria__tipo=tipo)
        ultimo = qs.select_related("categoria").order_by("-id").first()
        if ultimo and ultimo.categoria:
            usadas.append((getattr(ultimo, "data", None) or ultimo.data_lancamento, ultimo.categoria))
    if usadas:
        return max(usadas, key=lambda u: u[0])[1], "historico"
    return None, None


# Troca a categoria de um título (pago ou não) sem mexer no caixa; se o título veio de um
# lançamento, o lançamento também muda, porque é ele que o DRE lê. Fica registrado na observação.
def reclassificar_categoria(titulo, categoria, usuario=""):
    if categoria.tipo != titulo.tipo:
        raise FinanceiroErro("A nova categoria precisa ser do mesmo tipo (despesa ou receita).")
    anterior = titulo.categoria
    if anterior == categoria:
        raise FinanceiroErro("O título já está nesta categoria.")

    nota = (f"{timezone.localtime():%d/%m/%Y %H:%M} {usuario or 'usuário'}: categoria alterada de "
            f"\"{anterior.nome if anterior else 'sem categoria'}\" para \"{categoria.nome}\"")

    with transaction.atomic():
        titulo.categoria = categoria
        titulo.observacao = f"{titulo.observacao}\n{nota}".strip()
        titulo.save(update_fields=["categoria", "observacao"])

        if titulo.origem == "LANCAMENTO" and titulo.content_type_id == ContentType.objects.get_for_model(FinanceiroLancamento).id:
            lanc = FinanceiroLancamento.objects.filter(pk=titulo.object_id).first()
            if lanc:
                lanc.categoria = categoria
                lanc.observacao = f"{lanc.observacao or ''}\n{nota}".strip()
                lanc.save(update_fields=["categoria", "observacao"])
    return nota
