from django.shortcuts import render
from relatorios.forms import FiltroMovimentacaoEstoqueForm
from relatorios.services import estoque_service


def relatorio_movimentacoes_estoque(request):
    form = FiltroMovimentacaoEstoqueForm(request.GET or None)
    movimentacoes, resumo, totais = None, None, None

    if form.is_valid():
        dados = form.cleaned_data
        movimentacoes = estoque_service.movimentacoes_por_periodo(
            data_inicio=dados.get("data_inicio"),
            data_fim=dados.get("data_fim"),
            produto=dados.get("produto"),
            tipo=dados.get("tipo"),
            origem=dados.get("origem"),
        )
        resumo = estoque_service.resumo_por_produto(
            data_inicio=dados.get("data_inicio"),
            data_fim=dados.get("data_fim"),
            produto=dados.get("produto"),
        )
        totais = estoque_service.totais(movimentacoes)

    return render(request, "relatorios/estoque/movimentacoes.html", {
        "form": form,
        "movimentacoes": movimentacoes,
        "resumo": resumo,
        "totais": totais,
    })
