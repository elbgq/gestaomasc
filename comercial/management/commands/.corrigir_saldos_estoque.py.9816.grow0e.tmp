from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from comercial.models import Estoque, MovimentacaoEstoque


class Command(BaseCommand):
    help = (
        "Refaz o saldo e o preço médio dos produtos cujo saldo gravado não bate com as movimentações "
        "(mesma conta do verificar_estoque). Sem --aplicar, só mostra o que mudaria."
    )

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Grava a correção (sem isso, só simula).")

    def handle(self, *args, **options):
        aplicar = options["aplicar"]
        corrigidos = 0

        with transaction.atomic():
            for estoque in Estoque.objects.select_related("produto").order_by("produto__codor"):
                movs = MovimentacaoEstoque.objects.filter(produto=estoque.produto)
                entradas = movs.filter(tipo="ENTRADA").aggregate(t=Sum("quantidade"))["t"] or Decimal("0")
                saidas = movs.filter(tipo="SAIDA").aggregate(t=Sum("quantidade"))["t"] or Decimal("0")
                if entradas - saidas == estoque.quantidade:
                    continue

                antes = (estoque.quantidade, estoque.preco_medio)
                # Mesma rotina usada depois de estornos: percorre todas as movimentações do produto
                estoque.recalcular_preco_medio()
                corrigidos += 1
                self.stdout.write(
                    f"{estoque.produto}: saldo {antes[0]} -> {estoque.quantidade}, "
                    f"preço médio {antes[1]} -> {estoque.preco_medio}"
                )

            if not aplicar:
                transaction.set_rollback(True)

        if not corrigidos:
            self.stdout.write(self.style.SUCCESS("Todos os saldos conferem com as movimentações."))
        elif aplicar:
            self.stdout.write(self.style.SUCCESS(f"{corrigidos} produto(s) corrigido(s)."))
        else:
            self.stdout.write(self.style.WARNING(
                f"{corrigidos} produto(s) seriam corrigidos. Nada foi gravado; rode com --aplicar para gravar."
            ))
