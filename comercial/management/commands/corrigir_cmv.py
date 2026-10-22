from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Sum

from comercial.models import CMVItem, MovimentacaoEstoque, Venda, VendaItem


class Command(BaseCommand):
    help = (
        "Cria o CMV que falta nos itens de produto das vendas finalizadas, a partir da saída de estoque "
        "já registrada (custo médio do momento da saída), e acerta o CMV total de cada venda. "
        "Sem --aplicar, só mostra o que mudaria."
    )

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Grava as alterações.")

    def handle(self, aplicar, **options):
        criados = sem_saida = vendas_acertadas = 0

        with transaction.atomic():
            for venda in Venda.objects.filter(status="finalizada").order_by("numero"):
                com_cmv = set(CMVItem.objects.filter(venda=venda).values_list("item_id", flat=True))
                usadas = set()

                for item in venda.itens.filter(produto__isnull=False).exclude(id__in=com_cmv).order_by("id"):
                    # Saída desta venda para o produto; as antigas guardavam o id do item
                    mov = MovimentacaoEstoque.objects.filter(
                        Q(referencia_id=venda.id) | Q(referencia_id=item.id),
                        origem="VENDA", tipo="SAIDA", produto=item.produto, quantidade=item.quantidade,
                    ).exclude(id__in=usadas).order_by("id").first()

                    if mov is None or mov.preco_medio_apos is None:
                        sem_saida += 1
                        self.stdout.write(self.style.WARNING(
                            f"{venda.numero_formatado} item {item}: sem saída de estoque correspondente, verifique à mão."
                        ))
                        continue

                    usadas.add(mov.id)
                    total = (mov.preco_medio_apos * item.quantidade).quantize(Decimal("0.01"))
                    CMVItem.objects.create(
                        venda=venda, item=item, produto=item.produto, quantidade=item.quantidade,
                        custo_medio=mov.preco_medio_apos, total_cmv=total, data=venda.data_emissao,
                    )
                    VendaItem.objects.filter(pk=item.pk).update(custo_medio=mov.preco_medio_apos)
                    criados += 1
                    self.stdout.write(
                        f"{venda.numero_formatado} item {item}: CMV criado, {item.quantidade} × "
                        f"R$ {mov.preco_medio_apos} = R$ {total} (saída #{mov.id})"
                    )

                # CMV total da venda = soma do CMV dos itens
                cmv = CMVItem.objects.filter(venda=venda).aggregate(t=Sum("total_cmv"))["t"] or Decimal("0")
                cmv = Decimal(cmv).quantize(Decimal("0.01"))
                if cmv != venda.cmv:
                    self.stdout.write(f"{venda.numero_formatado}: CMV total de R$ {venda.cmv:.2f} para R$ {cmv:.2f}")
                    Venda.objects.filter(pk=venda.pk).update(cmv=cmv)
                    vendas_acertadas += 1

            if not aplicar:
                transaction.set_rollback(True)

        resumo = (f"{criados} CMV de item criado(s), {vendas_acertadas} venda(s) com CMV total acertado, "
                  f"{sem_saida} item(ns) para verificar à mão.")
        if aplicar:
            self.stdout.write(self.style.SUCCESS(resumo))
        else:
            self.stdout.write(resumo + " Nada foi gravado; rode de novo com --aplicar.")
