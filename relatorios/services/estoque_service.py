from decimal import Decimal

from comercial.models import Compra, CompraItem, MovimentacaoEstoque, Venda

# Nome de cada origem na tela; origens antigas ou desconhecidas aparecem como foram gravadas
ORIGENS = {
    "COMPRA": "Compra",
    "Compra": "Compra",
    "VENDA": "Venda",
    "VENDA_ESTORNADA": "Venda estornada",
    "ESTORNO_VENDA": "Estorno de venda",
    "AJUSTE": "Ajuste",
}

# Grupos do filtro de origem
FILTRO_ORIGEM = {
    "compra": ["COMPRA", "Compra"],
    "venda": ["VENDA", "VENDA_ESTORNADA"],
    "estorno": ["ESTORNO_VENDA"],
    "ajuste": ["AJUSTE"],
}


def _sinal(mov):
    return Decimal(mov.quantidade) if mov.tipo == "ENTRADA" else -Decimal(mov.quantidade)


# Custo da movimentação: a entrada pelo preço informado; a saída pelo custo médio do momento
def custo_unitario(mov):
    if mov.tipo == "ENTRADA":
        return mov.preco or Decimal("0")
    return mov.preco_medio_apos or Decimal("0")


def movimentacoes_por_periodo(data_inicio=None, data_fim=None, produto=None, tipo=None, origem=None):
    qs = MovimentacaoEstoque.objects.select_related("produto")

    if data_inicio:
        qs = qs.filter(data__date__gte=data_inicio)
    if data_fim:
        qs = qs.filter(data__date__lte=data_fim)
    if produto:
        qs = qs.filter(produto=produto)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if origem:
        qs = qs.filter(origem__in=FILTRO_ORIGEM.get(origem, [origem]))

    movs = list(qs.order_by("data", "id"))
    _anotar_documentos(movs)
    for mov in movs:
        mov.origem_nome = ORIGENS.get(mov.origem, mov.origem)
        mov.custo = custo_unitario(mov)
        mov.valor = (Decimal(mov.quantidade) * mov.custo).quantize(Decimal("0.01"))
    return movs


# Documento de cada movimentação (compra ou venda), para mostrar o número e o link
def _anotar_documentos(movs):
    vendas_ids = {m.referencia_id for m in movs if m.origem in ("VENDA", "VENDA_ESTORNADA", "ESTORNO_VENDA")}
    vendas = Venda.objects.in_bulk([i for i in vendas_ids if i])
    # Movimentações antigas ("Compra") guardam o id do item da compra; as novas, o id da compra
    itens_ids = {m.referencia_id for m in movs if m.origem == "Compra"}
    itens = CompraItem.objects.select_related("compra").in_bulk([i for i in itens_ids if i])
    compras_ids = {m.referencia_id for m in movs if m.origem == "COMPRA"}
    compras = Compra.objects.in_bulk([i for i in compras_ids if i])

    for mov in movs:
        mov.compra = mov.venda = None
        if mov.origem == "COMPRA":
            mov.compra = compras.get(mov.referencia_id)
        elif mov.origem == "Compra":
            item = itens.get(mov.referencia_id)
            mov.compra = item.compra if item else None
        elif mov.origem in ("VENDA", "VENDA_ESTORNADA", "ESTORNO_VENDA"):
            mov.venda = vendas.get(mov.referencia_id)


# Resumo por produto no período: saldo inicial, entradas, saídas e saldo final.
# Usa todas as movimentações do produto (sem os filtros de tipo e origem), para o saldo fechar.
def resumo_por_produto(data_inicio=None, data_fim=None, produto=None):
    qs = MovimentacaoEstoque.objects.select_related("produto")
    if produto:
        qs = qs.filter(produto=produto)
    if data_fim:
        qs = qs.filter(data__date__lte=data_fim)

    linhas = {}
    for mov in qs.order_by("data", "id"):
        linha = linhas.setdefault(mov.produto_id, {
            "produto": mov.produto, "saldo_inicial": Decimal("0"), "entradas": Decimal("0"),
            "saidas": Decimal("0"), "valor_entradas": Decimal("0"), "valor_saidas": Decimal("0"),
            "no_periodo": False,
        })
        if data_inicio and mov.data.date() < data_inicio:
            linha["saldo_inicial"] += _sinal(mov)
            continue
        linha["no_periodo"] = True
        valor = Decimal(mov.quantidade) * custo_unitario(mov)
        if mov.tipo == "ENTRADA":
            linha["entradas"] += Decimal(mov.quantidade)
            linha["valor_entradas"] += valor
        else:
            linha["saidas"] += Decimal(mov.quantidade)
            linha["valor_saidas"] += valor

    resumo = []
    for linha in linhas.values():
        if not linha["no_periodo"]:
            continue
        linha["saldo_final"] = linha["saldo_inicial"] + linha["entradas"] - linha["saidas"]
        resumo.append(linha)
    resumo.sort(key=lambda l: (l["produto"].descricao or "").upper())
    return resumo


def totais(movs):
    entradas = [m for m in movs if m.tipo == "ENTRADA"]
    saidas = [m for m in movs if m.tipo == "SAIDA"]
    return {
        "quantidade_entradas": sum((Decimal(m.quantidade) for m in entradas), Decimal("0")),
        "valor_entradas": sum((m.valor for m in entradas), Decimal("0")),
        "quantidade_saidas": sum((Decimal(m.quantidade) for m in saidas), Decimal("0")),
        "valor_saidas": sum((m.valor for m in saidas), Decimal("0")),
        "movimentacoes": len(movs),
    }
