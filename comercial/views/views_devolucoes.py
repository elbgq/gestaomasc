# comercial/views/views_devolucoes.py
#
# Telas da devolução de venda: registrar (com resumo do impacto antes de confirmar), listar,
# ver o detalhe e cancelar. As regras ficam em comercial/services/devolucoes.py.
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date

from comercial.forms import DevolucaoVendaForm
from comercial.models import Compra, Devolucao, PosVenda, Venda
from comercial.services.devolucoes import (
    DevolucaoErro, aviso_prazo, cancelar_devolucao, dados_do_xml, itens_devolviveis, itens_devolviveis_compra,
    planejar_devolucao_compra, planejar_devolucao_venda, reais, registrar_devolucao_compra,
    registrar_devolucao_venda, total_devolvido, total_devolvido_compra,
)
from financeiro.models import CaixaMovimento


def _quantidade(texto):
    try:
        return Decimal((texto or "0").strip().replace(",", ".") or "0")
    except InvalidOperation:
        return None


def devolucao_venda_criar(request, venda_id):
    venda = get_object_or_404(Venda.objects.select_related("cliente"), pk=venda_id)
    if venda.status != "finalizada":
        messages.error(request, "Só vendas finalizadas podem ter devolução.")
        return redirect("comercial:venda_detalhe", venda.id)

    linhas = itens_devolviveis(venda)
    if not any(l["disponivel"] > 0 for l in linhas):
        messages.info(request, "Todos os itens desta venda já foram devolvidos.")
        return redirect("comercial:venda_detalhe", venda.id)

    posvenda_id = request.POST.get("posvenda") or request.GET.get("posvenda")
    posvenda = PosVenda.objects.filter(pk=posvenda_id, venda=venda).first() if posvenda_id else None

    form = DevolucaoVendaForm(request.POST or None, request.FILES or None)
    plano, erro, xml = None, "", request.POST.get("xml_texto", "")

    if request.method == "POST":
        pedidos, invalidas = {}, []
        for linha in linhas:
            item = linha["item"]
            qtd = _quantidade(request.POST.get(f"qtd_{item.id}"))
            if qtd is None:
                invalidas.append(str(item.produto or item.servico))
                continue
            pedidos[item.id] = (qtd, request.POST.get(f"estoque_{item.id}") == "1")
            linha["pedido"], linha["volta"] = qtd, pedidos[item.id][1]

        if invalidas:
            erro = "Quantidade inválida em: " + ", ".join(invalidas)
        elif form.is_valid():
            xml = form.cleaned_data.get("xml") or xml
            dados = dict(form.cleaned_data, xml_nfe=xml, posvenda=posvenda)
            if xml and not dados.get("nf_chave"):
                dados["nf_chave"], numero = dados_do_xml(xml)
                dados["nf_numero"] = dados.get("nf_numero") or numero
            try:
                if request.POST.get("confirmar") == "1":
                    dev = registrar_devolucao_venda(venda, pedidos, dados, request.user)
                    messages.success(request, f"Devolução #{dev.id} registrada: R$ {reais(dev.valor_total)}.")
                    return redirect("comercial:devolucao_detalhe", dev.id)
                plano = planejar_devolucao_venda(venda, pedidos)
                if plano["restante"] > 0 and form.cleaned_data.get("acerto") not in ("reembolso", "credito"):
                    form.add_error("acerto", "O cliente já pagou parte do valor: escolha reembolso ou crédito.")
            except DevolucaoErro as e:
                erro, plano = str(e), None
    else:
        for linha in linhas:
            linha["pedido"], linha["volta"] = Decimal("0"), True

    data = (form.cleaned_data.get("data") if form.is_bound and form.is_valid() else None) or form["data"].value()
    if isinstance(data, str):
        data = parse_date(data)
    return render(request, "comercial/devolucao_form.html", {
        "venda": venda,
        "form": form,
        "linhas": linhas,
        "plano": plano,
        "erro": erro,
        "xml_texto": xml,
        "posvenda": posvenda,
        "ja_devolvido": total_devolvido(venda),
        "aviso": aviso_prazo(venda, data) if data else "",
        "ver_custos": request.user.has_perm("comercial.ver_custos"),
    })


# Devolução de compra: devolvemos ao fornecedor (a NF-e de devolução é nossa, CFOP 5.202/6.202)
ACERTO_COMPRA = (
    ("reembolso", "Reembolso do fornecedor (entra no caixa)"),
    ("credito", "Crédito com o fornecedor (conta a receber)"),
)


def devolucao_compra_criar(request, compra_id):
    compra = get_object_or_404(Compra.objects.select_related("fornecedor"), pk=compra_id)
    if not compra.confirmada:
        messages.error(request, "Só compras confirmadas podem ter devolução.")
        return redirect("comercial:compra_detalhe", compra.id)

    linhas = itens_devolviveis_compra(compra)
    if not any(l["disponivel"] > 0 for l in linhas):
        messages.info(request, "Todos os itens desta compra já foram devolvidos.")
        return redirect("comercial:compra_detalhe", compra.id)

    form = DevolucaoVendaForm(request.POST or None, request.FILES or None)
    form.fields["acerto"].choices = ACERTO_COMPRA
    form.fields["acerto"].help_text = "Só usado se a compra já foi paga. O resto abate as duplicatas em aberto."
    form.fields["nf_chave"].help_text = "NF-e de devolução emitida pela empresa para o fornecedor (CFOP 5.202 ou 6.202; com ST, 5.411 ou 6.411)."
    plano, erro, xml = None, "", request.POST.get("xml_texto", "")

    if request.method == "POST":
        pedidos, invalidas = {}, []
        for linha in linhas:
            item = linha["item"]
            qtd = _quantidade(request.POST.get(f"qtd_{item.id}"))
            if qtd is None:
                invalidas.append(item.descricao)
                continue
            pedidos[item.id] = linha["pedido"] = qtd

        if invalidas:
            erro = "Quantidade inválida em: " + ", ".join(invalidas)
        elif form.is_valid():
            xml = form.cleaned_data.get("xml") or xml
            dados = dict(form.cleaned_data, xml_nfe=xml)
            if xml and not dados.get("nf_chave"):
                dados["nf_chave"], numero = dados_do_xml(xml)
                dados["nf_numero"] = dados.get("nf_numero") or numero
            try:
                if request.POST.get("confirmar") == "1":
                    dev = registrar_devolucao_compra(compra, pedidos, dados, request.user)
                    messages.success(request, f"Devolução #{dev.id} registrada: R$ {reais(dev.valor_total)}.")
                    return redirect("comercial:devolucao_detalhe", dev.id)
                plano = planejar_devolucao_compra(compra, pedidos)
                if plano["restante"] > 0 and form.cleaned_data.get("acerto") not in ("reembolso", "credito"):
                    form.add_error("acerto", "A compra já foi paga em parte deste valor: escolha reembolso ou crédito.")
            except DevolucaoErro as e:
                erro, plano = str(e), None
    else:
        for linha in linhas:
            linha["pedido"] = Decimal("0")

    return render(request, "comercial/devolucao_compra_form.html", {
        "compra": compra,
        "form": form,
        "linhas": linhas,
        "plano": plano,
        "erro": erro,
        "xml_texto": xml,
        "ja_devolvido": total_devolvido_compra(compra),
    })


def devolucao_list(request):
    tipo = request.GET.get("tipo", "")
    status = request.GET.get("status", "confirmada")
    motivo = request.GET.get("motivo", "")
    q = request.GET.get("q", "").strip()
    de, ate = parse_date(request.GET.get("de") or ""), parse_date(request.GET.get("ate") or "")

    qs = Devolucao.objects.select_related("contato", "venda", "compra")
    if tipo:
        qs = qs.filter(tipo=tipo)
    if status in ("confirmada", "cancelada"):
        qs = qs.filter(status=status)
    if motivo:
        qs = qs.filter(motivo=motivo)
    if q:
        qs = qs.filter(Q(contato__nome__icontains=q) | Q(observacao__icontains=q) | Q(nf_numero=q))
    if de:
        qs = qs.filter(data__gte=de)
    if ate:
        qs = qs.filter(data__lte=ate)

    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "comercial/devolucao_list.html", {
        "page_obj": Paginator(qs, 20).get_page(request.GET.get("page")),
        "total": qs.filter(status="confirmada").aggregate(t=Sum("valor_total"))["t"] or Decimal("0"),
        "tipo": tipo, "status": status, "motivo": motivo, "q": q, "de": de, "ate": ate,
        "tipos": Devolucao.TIPO_CHOICES, "motivos": Devolucao.MOTIVO_CHOICES,
        "params": params.urlencode(),
    })


def devolucao_detalhe(request, pk):
    dev = get_object_or_404(Devolucao.objects.select_related("contato", "venda", "compra", "posvenda", "usuario"), pk=pk)
    return render(request, "comercial/devolucao_detalhe.html", {
        "dev": dev,
        "itens": dev.itens.select_related("produto", "servico"),
        "titulos": dev.titulos.select_related("receber", "pagar"),
        "caixa": CaixaMovimento.objects.filter(
            Q(origem="DEVOLUCAO") | Q(origem="ESTORNO", referencia_tipo__isnull=True), referencia_id=dev.id
        ).order_by("data", "id"),
        "ver_custos": request.user.has_perm("comercial.ver_custos"),
    })


def devolucao_cancelar(request, pk):
    dev = get_object_or_404(Devolucao, pk=pk)
    if dev.status != "confirmada":
        messages.error(request, "Esta devolução já foi cancelada.")
        return redirect("comercial:devolucao_detalhe", dev.id)

    if request.method == "POST":
        try:
            cancelar_devolucao(dev, request.user, request.POST.get("motivo", "").strip())
            messages.success(request, f"Devolução #{dev.id} cancelada.")
        except DevolucaoErro as e:
            messages.error(request, str(e))
        return redirect("comercial:devolucao_detalhe", dev.id)
    return render(request, "comercial/devolucao_cancelar.html", {"dev": dev})


def devolucao_xml(request, pk):
    dev = get_object_or_404(Devolucao, pk=pk)
    if not dev.xml_nfe:
        messages.error(request, "Esta devolução não tem XML.")
        return redirect("comercial:devolucao_detalhe", dev.id)
    resposta = HttpResponse(dev.xml_nfe, content_type="application/xml")
    resposta["Content-Disposition"] = f'attachment; filename="devolucao_{dev.id}_{dev.nf_chave or "nfe"}.xml"'
    return resposta
