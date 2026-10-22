from comercial.models import CMVItem


# CMV das vendas finalizadas, pela data da venda (as mesmas regras do DRE).
# __date inclui o último dia inteiro do período.
def cmv_por_periodo(data_inicio=None, data_fim=None, produto=None):
    qs = CMVItem.objects.filter(venda__status="finalizada").select_related("venda", "produto")

    if data_inicio:
        qs = qs.filter(data__date__gte=data_inicio)
    if data_fim:
        qs = qs.filter(data__date__lte=data_fim)
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
