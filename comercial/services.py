from decimal import Decimal, ROUND_HALF_UP
from financeiro.models import FinanceiroCategoria
from .models import Estoque, MovimentacaoEstoque

# Registrar venda
from django.utils import timezone


def registrar_compra(compra):

    categoria_compras, _ = FinanceiroCategoria.objects.get_or_create(
        nome="Compras",
        defaults={"tipo": "D"}
    )

    # 2. Processar itens
    for item in compra.itens.all():

        if not item.produto:
            continue

        estoque, _ = Estoque.objects.get_or_create(
            produto=item.produto,
            defaults={"quantidade": 0, "preco_medio": 0}
        )

        quantidade_atual = Decimal(estoque.quantidade)
        preco_medio_atual = Decimal(estoque.preco_medio)

        quantidade_compra = Decimal(item.quantidade)
        preco_compra = Decimal(item.preco_unitario)

        # cálculo do novo preço médio
        if quantidade_atual > 0:
            preco_medio_novo = (
                (quantidade_atual * preco_medio_atual) +
                (quantidade_compra * preco_compra)
            ) / (quantidade_atual + quantidade_compra)

            preco_medio_novo = preco_medio_novo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            preco_medio_novo = preco_compra

        # atualizar estoque
        estoque.quantidade = quantidade_atual + quantidade_compra
        estoque.preco_medio = preco_medio_novo
        estoque.save()

        # movimentação
        MovimentacaoEstoque.objects.create(
            produto=item.produto,
            tipo="ENTRADA",
            quantidade=item.quantidade,
            preco=item.preco_unitario,
            origem="Compra",
            referencia_id=item.id
        )

