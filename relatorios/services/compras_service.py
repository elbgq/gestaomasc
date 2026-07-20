# relatorios/services/compras_service.py
from django.db.models import Sum, F
from comercial.models import CompraItem  # ajuste o caminho

def compras_por_periodo(data_inicio=None, data_fim=None, fornecedor=None, numero_nota=None):
    qs = CompraItem.objects.select_related("compra", "compra__fornecedor", "produto")

    if data_inicio:
        qs = qs.filter(compra__data__gte=data_inicio)
    if data_fim:
        qs = qs.filter(compra__data__lte=data_fim)
    if fornecedor:
        qs = qs.filter(compra__fornecedor=fornecedor)
    if numero_nota:
        qs = qs.filter(compra__numero_nota__icontains=numero_nota)

    # Anota total por item (quantidade * preço_unitário)
    qs = qs.annotate(
        total_item=F("quantidade") * F("preco_unitario")
    )

    return qs


def resumo_totais(qs):
    """
    Recebe o queryset de itens de compra já filtrado
    e devolve totais agregados.
    """
    agregados = qs.aggregate(
        total_geral=Sum(F("quantidade") * F("preco_unitario")),
        total_quantidade=Sum("quantidade")
    )
    return agregados
