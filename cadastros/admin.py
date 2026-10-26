from django.contrib import admin
from .models import Produto, Servico, Contato, ConfiguracaoPreco, CategoriaServico, ReajusteServico

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ('codor', 'descricao', 'unidade', 'preco_venda', 'preco_manual', 'marca', )
    list_filter = ('unidade', 'marca', 'preco_manual')
    search_fields = ('descricao', 'marca')
    ordering = ('descricao',)


@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
    list_display = ('codsv', 'descricao', 'categoria', 'unidade', 'preco_servico', 'ano_tabela')
    list_filter = ('categoria', 'unidade')
    search_fields = ('descricao',)
    ordering = ('descricao',)


@admin.register(Contato)
class ContatoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "documento", "telefone", "email")
    search_fields = ("nome", "documento")
    list_filter = ("tipo",)



@admin.register(ConfiguracaoPreco)
class ConfiguracaoPrecoAdmin(admin.ModelAdmin):
    list_display = ("markup", "tolerancia")


@admin.register(CategoriaServico)
class CategoriaServicoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordem")
    ordering = ("ordem", "nome")


@admin.register(ReajusteServico)
class ReajusteServicoAdmin(admin.ModelAdmin):
    list_display = ("data", "servico", "ano_tabela", "preco_anterior", "preco_novo", "usuario")
    list_filter = ("ano_tabela",)
    search_fields = ("servico__descricao", "servico__codsv")
