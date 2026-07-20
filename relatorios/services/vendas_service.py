from django.db.models import Sum, F
from comercial.models import VendaItem  # ajuste conforme seu projeto

def vendas_por_periodo(data_inicio=None, data_fim=None, cliente=None, numero_nota=None):
    itens = VendaItem.objects.select_related("venda", "produto")

    if data_inicio:
        itens = itens.filter(venda__data_emissao__gte=data_inicio)
    if data_fim:
        itens = itens.filter(venda__data_emissao__lte=data_fim)
    if cliente:
        itens = itens.filter(venda__cliente=cliente)
    if numero_nota:
        itens = itens.filter(venda__numero_nota__icontains=numero_nota)

    return itens


# vendas_service.py

def resumo_totais(itens):
    if not itens:
        return {
            "total_quantidade": 0,
            "total_geral": 0,
        }

    total_quantidade = itens.aggregate(
        total=Sum("quantidade")
    )["total"] or 0

    total_geral = itens.aggregate(
        total=Sum(F("quantidade") * F("preco_unitario"))
    )["total"] or 0

    return {
        "total_quantidade": total_quantidade,
        "total_geral": total_geral,
    }
    