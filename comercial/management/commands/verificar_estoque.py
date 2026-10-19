from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from comercial.models import Estoque, MovimentacaoEstoque


class Command(BaseCommand):
    help = (
        "Compara o saldo gravado em Estoque com a soma das movimentações de cada produto. "
        "Apenas mostra as diferenças; não altera nada."
    )

    def handle(self, *args, **options):
        divergentes = 0

        for estoque in Estoque.objects.select_related("produto").order_by("produto__codor"):
            movs = MovimentacaoEstoque.objects.filter(produto=estoque.produto)
            entradas = movs.filter(tipo="ENTRADA").aggregate(t=Sum("quantidade"))["t"] or Decimal("0")
            # Saídas estornadas continuam no histórico e têm uma entrada de estorno correspondente
            saidas = movs.filter(tipo="SAIDA").aggregate(t=Sum("quantidade"))["t"] or Decimal("0")
            calculado = entradas - saidas

            if calculado != estoque.quantidade:
                divergentes += 1
                self.stdout.write(
                    f"{estoque.produto}: gravado {estoque.quantidade}, "
                    f"pelas movimentações {calculado} (diferença {estoque.quantidade - calculado})"
                )

        if divergentes:
            self.stdout.write(self.style.WARNING(f"{divergentes} produto(s) com saldo divergente."))
        else:
            self.stdout.write(self.style.SUCCESS("Todos os saldos conferem com as movimentações."))
