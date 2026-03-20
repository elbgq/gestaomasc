from django.contrib import admin
from .models import Produto, Servico, Contato

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ('codor', 'descricao', 'unidade', 'preco_venda', 'marca', )
    list_filter = ('unidade', 'marca')
    search_fields = ('descricao', 'marca')
    ordering = ('descricao',)


@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
    list_display = ('codsv', 'descricao', 'unidade', 'preco_servico')
    list_filter = ('unidade',)
    search_fields = ('descricao',)
    ordering = ('descricao',)


@admin.register(Contato)
class ContatoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "documento", "telefone", "email")
    search_fields = ("nome", "documento")
    list_filter = ("tipo",)

