# relatorios/views/compras.py
from django.shortcuts import render
from relatorios.forms import FiltroComprasForm
from relatorios.services import compras_service

def relatorio_compras_por_periodo(request):
    form = FiltroComprasForm(request.GET or None)
    itens = None
    totais = None

    if form.is_valid():
        itens = compras_service.compras_por_periodo(
            data_inicio=form.cleaned_data.get("data_inicio"),
            data_fim=form.cleaned_data.get("data_fim"),
            fornecedor=form.cleaned_data.get("fornecedor"),
            numero_nota=form.cleaned_data.get("numero_nota"),
        )
        totais = compras_service.resumo_totais(itens)

    context = {
        "form": form,
        "itens": itens,
        "totais": totais,
    }
    return render(request, "relatorios/compras/por_periodo.html", context)
