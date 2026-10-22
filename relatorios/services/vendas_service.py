from decimal import Decimal

from django.db.models import Sum, F
from comercial.models import Venda, VendaItem


# Itens das vendas finalizadas (as mesmas que entram no DRE); rascunhos e canceladas ficam de fora
def vendas_por_periodo(data_inicio=None, data_fim=None, cliente=None, numero_nota=None):
    itens = VendaItem.objects.filter(venda__status="finalizada").select_related(
        "venda", "venda__cliente", "produto", "servico"
    )

    if data_inicio:
        itens = itens.filter(venda__data_emissao__date__gte=data_inicio)
    if data_fim:
        itens = itens.filter(venda__data_emissao__date__lte=data_fim)
    if cliente:
        itens = itens.filter(venda__cliente=cliente)
    if numero_nota:
        # Venda não tem número de nota; o filtro usa o número da venda (ex.: V000012)
        digitos = "".join(c for c in numero_nota if c.isdigit())
        if digitos:
            itens = itens.filter(venda__numero=int(digitos))

    return itens.order_by("venda__data_emissao", "venda__numero", "id")


# Totais com a mesma conta das linhas (quantidade × preço - desconto do item) e,
# à parte, o desconto e o acréscimo dados na venda inteira
def resumo_totais(itens):
    somas = itens.aggregate(
        soma_quantidade=Sum("quantidade"),
        soma_itens=Sum(F("quantidade") * F("preco_unitario") - F("desconto")),
    )
    vendas = Venda.objects.filter(id__in=itens.values("venda_id")).aggregate(
        desconto=Sum("desconto"), acrescimo=Sum("acrescimo")
    )
    total_itens = somas["soma_itens"] or Decimal("0")
    desconto = vendas["desconto"] or Decimal("0")
    acrescimo = vendas["acrescimo"] or Decimal("0")

    return {
        "total_quantidade": somas["soma_quantidade"] or 0,
        "total_itens": total_itens,
        "desconto_vendas": desconto,
        "acrescimo_vendas": acrescimo,
        "total_geral": total_itens - desconto + acrescimo,
    }
