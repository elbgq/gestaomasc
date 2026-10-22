# Preço de venda automático: preço = custo médio do estoque × (1 + markup/100).
# O markup e a tolerância ficam em ConfiguracaoPreco (tela Revisão de preços).
# Produto com preco_manual marcado nunca é recalculado; só aparece sinalizado.
from .models import ConfiguracaoPreco


# Recalcula o preço de um produto automático. Devolve (antigo, novo) se mudou, senão None.
# Chamado sempre que o custo médio muda (entrada de compra e recálculo do estoque).
def atualizar_preco_venda(produto, config=None):
    if produto.preco_manual:
        return None
    sugerido = produto.preco_sugerido(config)
    if sugerido is None or sugerido == produto.preco_venda:
        return None
    antigo = produto.preco_venda
    produto.preco_venda = sugerido
    produto.save(update_fields=["preco_venda"])
    return antigo, sugerido


# Recalcula todos os produtos automáticos (ex.: depois de mudar o markup). Devolve quantos mudaram.
def recalcular_precos_automaticos():
    from .models import Produto

    config = ConfiguracaoPreco.atual()
    return sum(
        1 for produto in Produto.objects.filter(preco_manual=False)
        if atualizar_preco_venda(produto, config)
    )


# Produtos com preço abaixo do custo ou manual fora da tolerância, com os números da revisão
def produtos_sinalizados(produtos):
    config = ConfiguracaoPreco.atual()
    linhas = []
    for produto in produtos:
        situacao = produto.situacao_preco(config)
        if situacao:
            linhas.append({
                "produto": produto,
                "situacao": situacao,
                "custo": produto.custo_medio,
                "sugerido": produto.preco_sugerido(config),
                "diferenca": produto.diferenca_sugerido(config),
            })
    return linhas
