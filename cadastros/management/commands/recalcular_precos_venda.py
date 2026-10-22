from django.core.management.base import BaseCommand
from django.db import transaction

from cadastros.models import ConfiguracaoPreco, Produto
from cadastros.precos import atualizar_preco_venda


class Command(BaseCommand):
    help = (
        "Lista o preço atual e o sugerido (custo médio + markup) de cada produto. "
        "Com --aplicar, recalcula os produtos de preço automático; os manuais nunca mudam."
    )

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Grava os preços dos produtos automáticos.")

    def handle(self, aplicar, **options):
        config = ConfiguracaoPreco.atual()
        self.stdout.write(f"Markup {config.markup}% · tolerância {config.tolerancia}%")
        alterados = 0

        with transaction.atomic():
            for produto in Produto.objects.order_by("descricao").prefetch_related("estoque_set"):
                sugerido = produto.preco_sugerido(config)
                tipo = "manual" if produto.preco_manual else "auto"
                situacao = {"abaixo_custo": "  ABAIXO DO CUSTO", "fora_sugerido": "  FORA DO SUGERIDO"}.get(
                    produto.situacao_preco(config), ""
                )
                self.stdout.write(
                    f"[{tipo:6}] {produto}: custo {produto.custo_medio:.2f} · atual {produto.preco_venda:.2f} · "
                    f"sugerido {sugerido if sugerido is not None else '-'}{situacao}"
                )
                if aplicar and atualizar_preco_venda(produto, config):
                    alterados += 1

            if aplicar:
                self.stdout.write(self.style.SUCCESS(f"{alterados} produto(s) automático(s) com preço alterado."))
            else:
                self.stdout.write("Nada foi gravado. Use --aplicar para recalcular os produtos automáticos.")
