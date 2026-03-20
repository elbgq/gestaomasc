from django.contrib import admin
from comercial.models import(
    Compra, CompraItem, Estoque, MovimentacaoEstoque, Venda, VendaItem, CMVItem
    )


# Register your models here.

# ============================
# INLINES
# ============================
class CompraItemInline(admin.TabularInline):
    model = CompraItem
    extra = 0

class VendaItemInline(admin.TabularInline):
    model = VendaItem
    extra = 0
    autocomplete_fields = ["produto"]

# ============================
# ADMINS
# ============================
@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ("numero_nota", "fornecedor", "data", "valor_total")
    inlines = [CompraItemInline]
    
    
@admin.register(Estoque)
class EstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "quantidade", "preco_medio")
    search_fields = ("produto__descricao",)
    list_filter = ("produto",)

@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "data",
        "produto",
        "tipo",
        "quantidade",
        "preco",
        "origem",
        "referencia_id",
        "saldo_apos",
        "preco_medio_apos",
    )
    search_fields = ("produto__descricao", "origem")
    list_filter = ("tipo", "origem", "produto")
    ordering = ("-data",)

    
@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "data_emissao", "total", "status")
    list_filter = ("data_emissao", "status")
    search_fields = ("cliente__nome", "id")
    inlines = [VendaItemInline]
    
@admin.register(CMVItem)
class CMVItemAdmin(admin.ModelAdmin):
    list_display = ("produto", "quantidade", "custo_medio", "total_cmv", "data")
    search_fields = ("produto",)
    ordering = ("-data",)