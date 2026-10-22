# relatorios/services/compras_service.py
from django.db.models import Sum, F
from comercial.models import CompraItem

# Valor do item na nota: produtos + frete + seguro + outras despesas + IPI + ICMS-ST - desconto
# (o mesmo cálculo de CompraItem.valor_nota, que soma o total da compra)
VALOR_NOTA = (
    F("total") + F("valor_frete") + F("valor_seguro") + F("valor_outras")
    + F("valor_ipi") + F("valor_icms_st") - F("valor_desconto")
)


# Itens das compras confirmadas (as que já entraram no estoque e no contas a pagar)
def compras_por_periodo(data_inicio=None, data_fim=None, fornecedor=None, numero_nota=None):
    qs = CompraItem.objects.filter(compra__confirmada=True).select_related(
        "compra", "compra__fornecedor", "produto"
    )

    if data_inicio:
        qs = qs.filter(compra__data__gte=data_inicio)
    if data_fim:
        qs = qs.filter(compra__data__lte=data_fim)
    if fornecedor:
        qs = qs.filter(compra__fornecedor=fornecedor)
    if numero_nota:
        qs = qs.filter(compra__numero_nota__icontains=numero_nota)

    return qs.annotate(total_item=VALOR_NOTA).order_by("compra__data", "compra_id", "id")


def resumo_totais(qs):
    """
    Recebe o queryset de itens de compra já filtrado
    e devolve totais agregados.
    """
    agregados = qs.aggregate(
        total_produtos=Sum("total"),
        total_geral=Sum(VALOR_NOTA),
        total_quantidade=Sum("quantidade"),
    )
    return agregados
