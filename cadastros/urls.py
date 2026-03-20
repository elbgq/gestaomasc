
# cadastros/urls.py
from django.urls import path
from . import views

# Importar Produtos e Serviços via CSV
from .views import (
    importar_produtos,
    importar_servicos, 
    produto_create_ajax
)

from .views import (
    contato_list,
    contato_detail,
    contato_create,
    contato_update,
    contato_delete,
)


app_name = "cadastros"

urlpatterns = [
    # Produtos
    path("produtos/", views.ProdutoListView.as_view(), name="produto_list"),
    path("produtos/novo/", views.produto_create, name="produto_create"),
    path("produtos/novo/ajax/", produto_create_ajax, name="produto_create_ajax"),
    path("produtos/<int:pk>/", views.ProdutoDetailView.as_view(), name="produto_detail"),
    path("produtos/<int:pk>/editar/", views.produto_update, name="produto_update"),
    path("produtos/<int:pk>/excluir/", views.produto_delete, name="produto_delete"),
    
    # Importar Produtos via CSV
    path('produtos/importar/', importar_produtos, name='importar_produtos'),

    # Serviços
    path("servicos/", views.servico_list, name="servico_list"),
    path("servicos/novo/", views.servico_create, name="servico_create"),
    path("servicos/<int:pk>/", views.servico_detail, name="servico_detail"),
    path("servicos/<int:pk>/editar/", views.servico_update, name="servico_update"),
    path("servicos/<int:pk>/excluir/", views.servico_delete, name="servico_delete"),
    
    # Importar Serviços via CSV
    path('servicos/importar/', importar_servicos, name='importar_servicos'),
    
    # Contatos
    path("contatos/", contato_list, name="contato_list"),
    path("contatos/novo/", contato_create, name="contato_create"),
    path("contatos/<int:pk>/", contato_detail, name="contato_detail"),
    path("contatos/<int:pk>/editar/", contato_update, name="contato_update"),
    path("contatos/<int:pk>/excluir/", contato_delete, name="contato_delete")
]
