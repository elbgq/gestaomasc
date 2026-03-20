# comercial/urls.py

from django.urls import path
from .views.views_vendas import (  
    venda_create, venda_editar, venda_detalhe,
    venda_parcelamento,  venda_list, venda_excluir,
    venda_recibo, dashboard_comercial, api_preco 
)
from .views.views_estoque import (
    EstoqueListView, MovimentacaoEstoqueListView, estoque_relatorio,
    ajax_estoque, cmv_lista, cmv_detalhe, relatorio_estoque
)
from .views.views_compras import (
    criar_compra, editar_compra, compra_excluir, compra_list, compra_detalhe,
    importar_compra, vincular_itens, confirmar_compra, compra_finalizar_avista,
    compra_finalizar_parcelada
)



app_name = "comercial"
 
urlpatterns = [
    
    # Importar Compras
    path("compras/importar/", importar_compra, name="compras_importar"),
    
    # Compras de Produtos
    path('compras/', compra_list, name='compra_list'),
    path("compras/novo/", criar_compra, name="compra_criar"),
    path("compras/<int:compra_id>/editar/", editar_compra, name="compra_editar"),
    path("compras/<int:compra_id>/", compra_detalhe, name="compra_detalhe"),
    path("compras/<int:compra_id>/excluir/", compra_excluir, name="compra_excluir"),  # se existir
    path("compras/<int:compra_id>/finalizar/avista/", compra_finalizar_avista, name="compras_finalizar_avista"),
    path("compras/<int:compra_id>/finalizar/parcelado/", compra_finalizar_parcelada, name="compras_finalizar_parcelado"),
    path("compras/<int:compra_id>/vincular_itens/", vincular_itens, name="vincular_itens"),
    path("compras/<int:compra_id>/confirmar_compra/", confirmar_compra, name="compras_confirmar"),
    
    # Estoque
    path('estoque/', EstoqueListView.as_view(), name='estoque_list'),
    path('movimentacao/', MovimentacaoEstoqueListView.as_view(), name='movimentacao_list'),
    path("estoque/relatorio/", relatorio_estoque, name="estoque_relatorio"),
    path("ajax/estoque/<int:produto_id>/", ajax_estoque, name="ajax_estoque"),
    
    #Vendas de produtos e serviços
    # Listagem e criação de vendas
    path("vendas/", venda_list, name="venda_list"),
    path("venda/nova/", venda_create, name="venda_create"),
    # Destalhes e edição de vendas
    path("venda/<int:venda_id>/editar/", venda_editar, name="venda_editar"),
    path("venda/<int:venda_id>/", venda_detalhe, name="venda_detalhe"),
    # Parcelamento de vendas
    path("venda/<int:venda_id>/parcelamento/", venda_parcelamento, name="venda_parcelamento"),
    # Exclusão de vendas
    path("venda/<int:venda_id>/excluir/", venda_excluir, name="venda_excluir"),
    # Recibo de venda
    path("venda/<int:venda_id>/recibo/", venda_recibo, name="venda_recibo"),
    # APIs auxiliares
    path("api/preco/<str:tipo>/<int:pk>/", api_preco, name="api_preco"),

    # CMV
    path("cmv/", cmv_lista, name="cmv_lista"),
    path("cmv/<int:venda_id>/", cmv_detalhe, name="cmv_detalhe"),    
         
    # Dashboard
    #path('', dashboard_comercial, name='dashboard'),
    
]
