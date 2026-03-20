from django.shortcuts import render
from relatorios.forms import FiltroCMVForm
from relatorios.services import cmv_service
from comercial.models import CMVItem

def relatorio_cmv(request):
    form = FiltroCMVForm(request.GET or None)
    itens = []
    totais = {"total_quantidade": 0, "total_cmv": 0}

    if form.is_valid():
        qs = CMVItem.objects.all()
        if form.cleaned_data.get("data_inicio"):
            qs = qs.filter(data__gte=form.cleaned_data["data_inicio"])

        if form.cleaned_data.get("data_fim"):
            qs = qs.filter(data__lte=form.cleaned_data["data_fim"])

        if form.cleaned_data.get("produto"):
            qs = qs.filter(produto=form.cleaned_data["produto"])

        itens = qs

        totais = {
            "total_quantidade": sum(i.quantidade for i in qs),
            "total_cmv": sum(i.total_cmv for i in qs),
        }


    return render(request, "relatorios/cmv/cmv_relatorio.html", {
        "form": form,
        "itens": itens,
        "totais": totais,
    })
    