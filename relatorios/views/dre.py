from django.shortcuts import render
from django.utils.http import urlencode
from types import SimpleNamespace
from relatorios.forms import FiltroDREForm
from relatorios.services.dre_service import dre_por_periodo


def relatorio_dre(request):
    form = FiltroDREForm(request.GET or None)
    dre = None
    periodo = ""
 
    if form.is_valid():
        dados = dre_por_periodo(
            form.cleaned_data["data_inicio"],
            form.cleaned_data["data_fim"]
        )
        dre = SimpleNamespace(**dados)
        # Período para os links das linhas de juros, multas e descontos (relatório de origem)
        periodo = urlencode({"data_inicio": form.cleaned_data["data_inicio"], "data_fim": form.cleaned_data["data_fim"]})


    return render(request, "relatorios/dre/dre.html", {
        "form": form,
        "dre": dre,
        "periodo": periodo,
    })
    