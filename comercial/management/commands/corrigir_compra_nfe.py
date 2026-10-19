import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comercial.models import Compra, Estoque, MovimentacaoEstoque
from comercial.services.xml_importer import NS, XmlCompraImporter
from financeiro.models import FinanceiroPagar

CENTAVO = Decimal("0.01")


class Command(BaseCommand):
    help = (
        "Recalcula uma compra importada antes da etapa B (frete, seguro, outras despesas, desconto, IPI e ST): "
        "total da compra, custo das entradas no estoque, custo médio atual dos produtos e parcelas pendentes. "
        "Sem --aplicar, só mostra o que mudaria."
    )

    def add_arguments(self, parser):
        parser.add_argument("compra_id", type=int)
        parser.add_argument("--aplicar", action="store_true", help="Grava as alterações.")

    def handle(self, compra_id, aplicar, **options):
        compra = Compra.objects.filter(id=compra_id).first()
        if not compra or not compra.importada or not compra.xml_nfe:
            raise CommandError("Compra não encontrada ou sem XML de NF-e guardado.")

        dets = ET.fromstring(compra.xml_nfe.encode("utf-8")).findall(".//nfe:det", NS)
        itens = list(compra.itens.select_related("produto").order_by("id"))
        if len(dets) != len(itens):
            raise CommandError(f"A nota tem {len(dets)} itens e a compra {len(itens)}; não é possível corrigir.")

        titulos = list(FinanceiroPagar.objects.filter(compra=compra).order_by("data_vencimento", "id"))
        if any(t.status != "pendente" for t in titulos):
            raise CommandError("Há parcelas desta compra já pagas. Ajuste manualmente em Contas a Pagar.")

        leitor = XmlCompraImporter(None)
        total_antigo = compra.valor_total

        with transaction.atomic():
            for det, item in zip(dets, itens):
                for campo, valor in leitor._valores_item(det).items():
                    setattr(item, campo, valor)
                item.save(update_fields=list(leitor._valores_item(det)))
                leitor._usar_total_da_nota(item, det)

            compra.valor_total = sum((item.valor_nota for item in itens), Decimal("0"))
            compra.save(update_fields=["valor_total"])
            self.stdout.write(f"Total da compra: R$ {total_antigo} -> R$ {compra.valor_total}")

            if compra.confirmada:
                self._corrigir_estoque(compra, itens)
                self._corrigir_parcelas(compra, titulos)

            if not aplicar:
                transaction.set_rollback(True)

        if aplicar:
            self.stdout.write(self.style.SUCCESS("Correção gravada."))
        else:
            self.stdout.write(self.style.WARNING("Nada foi gravado. Rode de novo com --aplicar para gravar."))

    def _corrigir_estoque(self, compra, itens):
        por_produto = {}
        for item in itens:
            if item.produto:
                custo, qtd = por_produto.get(item.produto, (Decimal("0"), Decimal("0")))
                por_produto[item.produto] = (custo + item.custo_total, qtd + item.quantidade_estoque)

        for produto, (custo, qtd) in por_produto.items():
            if not qtd:
                continue
            preco = (custo / qtd).quantize(CENTAVO, rounding=ROUND_HALF_UP)
            entradas = list(MovimentacaoEstoque.objects.filter(
                produto=produto, tipo="ENTRADA", origem="COMPRA", referencia_id=compra.id
            ))
            # Diferença de custo que entrou a mais (ou a menos) no estoque por esta compra
            diferenca = sum((Decimal(m.quantidade) * (Decimal(m.preco or 0) - preco) for m in entradas), Decimal("0"))
            for mov in entradas:
                mov.preco = preco
                mov.save(update_fields=["preco"])

            estoque = Estoque.objects.filter(produto=produto).first()
            if not estoque or not estoque.quantidade or not diferenca:
                continue
            if entradas and MovimentacaoEstoque.objects.filter(
                produto=produto, tipo="SAIDA", id__gt=min(m.id for m in entradas)
            ).exists():
                self.stdout.write(self.style.WARNING(
                    f"  {produto}: já teve vendas depois desta compra; o custo dessas vendas (CMV) não foi alterado."
                ))
            antigo = estoque.preco_medio
            estoque.preco_medio = (
                Decimal(antigo) - diferenca / Decimal(estoque.quantidade)
            ).quantize(CENTAVO, rounding=ROUND_HALF_UP)
            estoque.save(update_fields=["preco_medio"])
            self.stdout.write(f"  {produto}: custo médio R$ {antigo} -> R$ {estoque.preco_medio}")

    def _corrigir_parcelas(self, compra, titulos):
        if not titulos:
            return
        n = len(titulos)
        valor = (compra.valor_total / n).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        ajuste = compra.valor_total - valor * n
        for i, titulo in enumerate(titulos):
            novo = valor + (ajuste if i == n - 1 else Decimal("0"))
            self.stdout.write(f"  Parcela {titulo.data_vencimento:%d/%m/%Y}: R$ {titulo.valor} -> R$ {novo}")
            titulo.valor = novo
            titulo.save(update_fields=["valor"])
