from django.db.models import F, Sum
from decimal import Decimal
from comercial.models import VendaItem, MovimentacaoEstoque, CMVItem

def cmv_por_periodo(data_inicio=None, data_fim=None, produto=None):
    qs = CMVItem.objects.select_related("venda", "item", "produto")

    if data_inicio:
        qs = qs.filter(venda__data_emissao__gte=data_inicio)
    if data_fim:
        qs = qs.filter(venda__data_emissao__lte=data_fim)
    if produto:
        qs = qs.filter(produto=produto)

    return qs


def resumo_cmv(itens):
    total_quantidade = sum(i.quantidade for i in itens)
    total_cmv = sum(i.total_cmv for i in itens)

    return {
        "total_quantidade": total_quantidade,
        "total_cmv": total_cmv,
    }
