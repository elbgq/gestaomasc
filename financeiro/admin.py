from django.contrib import admin
from django.contrib import admin
from .models import (
    FinanceiroLancamento,
    FinanceiroPagar,
    FinanceiroReceber,
    CaixaMovimento,
    FinanceiroCategoria,
    Caixa,
)
 
@admin.register(FinanceiroLancamento)
class FinanceiroLancamentoAdmin(admin.ModelAdmin):
    list_display = ("id", "data", "descricao", "categoria", "valor", "origem")
    list_filter = ("categoria", "origem")
    search_fields = ("descricao",)


@admin.register(FinanceiroPagar)
class FinanceiroPagarAdmin(admin.ModelAdmin):
    list_display = ("descricao", "valor", "data_vencimento", "contato", "categoria")
    list_filter = ("data_vencimento", "contato")
    search_fields = ("descricao",)

    def origem_display(self, obj):
        if obj.compra:
            return f"Compra #{obj.compra.id}"

        if obj.referencia:
            return f"{obj.content_type.model} #{obj.object_id}"

        return "-"
    
    origem_display.short_description = "Origem"


@admin.register(FinanceiroReceber)
class FinanceiroReceberAdmin(admin.ModelAdmin):
    list_display = ("id", "descricao", "valor", "data_vencimento", "status", "origem")
    list_filter = ("status", "origem", "categoria")
    search_fields = ("descricao",)


@admin.register(CaixaMovimento)
class CaixaMovimentoAdmin(admin.ModelAdmin):
    list_display = ("id", "data", "descricao", "tipo", "valor", "origem", "referencia_id", "referencia_tipo")
    list_filter = ("tipo", "origem")
    search_fields = ("descricao",)


@admin.register(FinanceiroCategoria)
class FinanceiroCategoriaAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "tipo")
    list_filter = ("tipo",)
    search_fields = ("nome",)
# =======================

@admin.register(Caixa)
class CaixaAdmin(admin.ModelAdmin):
    list_display = ("nome", "saldo_inicial", "data_abertura", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome",)
