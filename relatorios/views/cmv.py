from django.shortcuts import render
from relatorios.forms import FiltroCMVForm
from relatorios.services import cmv_service


def relatorio_cmv(request):
    form = FiltroCMVForm(request.GET or None)
    itens = []
    totais = {"total_quantidade": 0, "total_cmv": 0}

    if form.is_valid():
        itens = list(cmv_service.cmv_por_periodo(
            data_inicio=form.cleaned_data.get("data_inicio"),
            data_fim=form.cleaned_data.get("data_fim"),
            produto=form.cleaned_data.get("produto"),
        ))
        totais = cmv_service.resumo_cmv(itens)

    return render(request, "relatorios/cmv/cmv_relatorio.html", {
        "form": form,
        "itens": itens,
        "totais": totais,
    })
