from django.urls import path
from relatorios.views import compras, vendas, cmv
from relatorios.views.dre import relatorio_dre

app_name = "relatorios"

urlpatterns = [
    path("compras/por-periodo/", compras.relatorio_compras_por_periodo, name="compras_por_periodo"),
    path("vendas/por-periodo/", vendas.relatorio_vendas_por_periodo, name="vendas_por_periodo"),
    path("cmv/por-periodo/", cmv.relatorio_cmv, name="cmv_relatorio"),
    path("dre/", relatorio_dre, name="dre"),
]

