# financeiro/urls.py
from django.urls import path
from .views_categoria import (
    CategoriaListView, CategoriaCreateView,
    CategoriaUpdateView, CategoriaDeleteView
)
from .views_lancamento import (
    LancamentoListView, LancamentoCreateView,
    LancamentoUpdateView, LancamentoDeleteView
)
from .views_receber import (
    ReceberListView, ReceberCreateView,
    ReceberUpdateView, ReceberDeleteView
)

from .views_caixa import(
    caixa_detalhe, caixa_list, caixa_historico,
    CaixaCreateView, CaixaUpdateView, CaixaDeleteView,
    dashboard_financeiro, caixa_movimento_detalhe, caixa_abrir
)

from .views_contas_pagar import (
    contas_pagar_lista, titulo_detalhe, pagar_titulo,
    pagar_delete, pagar_update, conta_detalhe
)
from .views_titulos import(
    TituloListView, TituloDetailView, titulo_quitacao_view
)

app_name = "financeiro"

urlpatterns = [
    # URLs das views de Categoria
    path("categorias/", CategoriaListView.as_view(), name="categoria_list"),
    path("categorias/novo/", CategoriaCreateView.as_view(), name="categoria_create"),
    path("categorias/<int:pk>/editar/", CategoriaUpdateView.as_view(), name="categoria_update"),
    path("categorias/<int:pk>/excluir/", CategoriaDeleteView.as_view(), name="categoria_delete"),
    
    # URLs das views de Lançamento
    path("lancamentos/", LancamentoListView.as_view(), name="lancamento_list"),
    path("lancamentos/novo/", LancamentoCreateView.as_view(), name="lancamento_create"),
    path("lancamentos/<int:pk>/editar/", LancamentoUpdateView.as_view(), name="lancamento_update"),
    path("lancamentos/<int:pk>/excluir/", LancamentoDeleteView.as_view(), name="lancamento_delete"),
    
    # URLs das views de Receber
    path("receber/", ReceberListView.as_view(), name="receber_list"),
    path("receber/novo/", ReceberCreateView.as_view(), name="receber_create"),
    path("receber/<int:pk>/editar/", ReceberUpdateView.as_view(), name="receber_update"),
    path("receber/<int:pk>/excluir/", ReceberDeleteView.as_view(), name="receber_delete"),
     
    # URLs das views de Pagar
    path("contas-pagar/", contas_pagar_lista, name="contas_pagar_lista"),
    path("contas-pagar/<int:pk>/editar/", pagar_update, name="pagar_update"),
    path("contas-pagar/<int:pk>/excluir/", pagar_delete, name="pagar_delete"),
    path("contas-pagar/<int:pk>/pagar/", pagar_titulo, name="pagar_titulo"),
    
    path("contas/<int:conta_id>/", conta_detalhe, name="conta_detalhe"),
    
    # URLs da views do caixa 

    # LISTAGEM DO CAIXA
    path("caixa/", caixa_list, name="caixa_list"),

    # DETALHE DO MOVIMENTO
    path("caixa/<int:pk>/", caixa_detalhe, name="caixa_detalhe"),

    # HISTÓRICO DO CAIXA
    path("caixa/historico/", caixa_historico, name="caixa_historico"),

    # CRIAR MOVIMENTO MANUAL
    path("caixa/novo/", CaixaCreateView.as_view(), name="caixa_create"),

    # EDITAR MOVIMENTO MANUAL
    path("caixa/<int:pk>/editar/", CaixaUpdateView.as_view(), name="caixa_update"),

    # EXCLUIR MOVIMENTO MANUAL
    path("caixa/<int:pk>/excluir/", CaixaDeleteView.as_view(), name="caixa_delete"),
    
    path("caixa/movimento/<int:pk>/", caixa_movimento_detalhe, name="caixa_movimento_detalhe"),
    
    path("caixa/<int:pk>/abrir/", caixa_abrir, name="caixa_abrir"),
    
    # DASHBOARD FINANCEIRO
    path("dashboard/", dashboard_financeiro, name="dashboard"),
    
    # Títulos 
    path("titulos/", TituloListView.as_view(), name="titulo_list"),
    path("titulos/<str:tipo>/<int:pk>/quitar/", titulo_quitacao_view, name="titulo_confirmar_quitacao"),
    path("titulos/<str:tipo>/<int:pk>/", TituloDetailView.as_view(), name="titulo_detalhe"),

]


