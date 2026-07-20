from django.shortcuts import render
from relatorios.forms import FiltroVendasForm
from relatorios.services import vendas_service

def relatorio_vendas_por_periodo(request):
    form = FiltroVendasForm(request.GET or None)
    itens = None
    totais = None

    if form.is_valid():
        itens = vendas_service.vendas_por_periodo(
            data_inicio=form.cleaned_data.get("data_inicio"),
            data_fim=form.cleaned_data.get("data_fim"),
            cliente=form.cleaned_data.get("cliente"),
            numero_nota=form.cleaned_data.get("numero_nota"),
        )
        totais = vendas_service.resumo_totais(itens)

    return render(request, "relatorios/vendas/por_periodo.html", {
        "form": form,
        "itens": itens,
        "totais": totais,
    })
    