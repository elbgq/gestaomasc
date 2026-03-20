from django.shortcuts import render
from types import SimpleNamespace
from relatorios.forms import FiltroDREForm
from relatorios.services.dre_service import dre_por_periodo


def relatorio_dre(request):
    form = FiltroDREForm(request.GET or None)
    dre = None
 
    if form.is_valid():
        dados = dre_por_periodo(
            form.cleaned_data["data_inicio"],
            form.cleaned_data["data_fim"]
        )
        dre = SimpleNamespace(**dados)


    return render(request, "relatorios/dre/dre.html", {
        "form": form,
        "dre": dre
    })
    