from django.urls import path
from relatorios.views import compras, vendas, cmv, estoque
from relatorios.views.dre import relatorio_dre
from relatorios.views.juros import relatorio_juros_multas

app_name = "relatorios"

urlpatterns = [
    path("compras/por-periodo/", compras.relatorio_compras_por_periodo, name="compras_por_periodo"),
    path("vendas/por-periodo/", vendas.relatorio_vendas_por_periodo, name="vendas_por_periodo"),
    path("cmv/por-periodo/", cmv.relatorio_cmv, name="cmv_relatorio"),
    path("dre/", relatorio_dre, name="dre"),
    path("juros-multas/", relatorio_juros_multas, name="juros_multas"),
    path("estoque/movimentacoes/", estoque.relatorio_movimentacoes_estoque, name="movimentacoes_estoque"),
]

