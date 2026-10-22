from django.core.management.base import BaseCommand
from django.db import transaction

from financeiro.models import CaixaMovimento, FinanceiroPagar, FinanceiroReceber


class Command(BaseCommand):
    help = (
        "Liga os títulos já quitados ao movimento de caixa da quitação (quitações feitas pela tela "
        "Títulos antes da correção). Sem --aplicar, só mostra o que mudaria."
    )

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Grava as alterações.")

    def handle(self, aplicar, **options):
        ligados = sem_movimento = 0

        with transaction.atomic():
            for modelo, tipo, origem in ((FinanceiroPagar, "D", "PAGAMENTO"), (FinanceiroReceber, "R", "RECEITA")):
                for titulo in modelo.objects.filter(status="pago", caixa_movimento__isnull=True).order_by("id"):
                    movs = list(CaixaMovimento.objects.filter(
                        origem=origem, referencia_tipo=tipo, referencia_id=titulo.id
                    ).order_by("id"))
                    if not movs:
                        movs = self.movimentos_orfaos(modelo, tipo, origem, titulo)

                    if len(movs) != 1:
                        sem_movimento += 1
                        self.stdout.write(self.style.WARNING(
                            f"{tipo} #{titulo.id} {titulo.descricao}: {len(movs)} movimentos encontrados, verifique à mão."
                        ))
                        continue

                    mov = movs[0]
                    avisos = []
                    if mov.valor != titulo.valor_pago:
                        avisos.append(f"valor do movimento R$ {mov.valor} difere do pago R$ {titulo.valor_pago}")
                    if mov.data != titulo.data_pagamento:
                        avisos.append(f"data do movimento {mov.data:%d/%m/%Y} difere da quitação "
                                      f"{titulo.data_pagamento:%d/%m/%Y}" if titulo.data_pagamento else
                                      "título sem data de quitação")
                    if mov.referencia_id != titulo.id:
                        avisos.append(f"o movimento apontava para o título #{mov.referencia_id}, que não existe mais")
                        mov.referencia_id = titulo.id
                        mov.save(update_fields=["referencia_id"])
                    titulo.caixa_movimento = mov
                    titulo.save(update_fields=["caixa_movimento"])
                    self.stdout.write(
                        f"{tipo} #{titulo.id} {titulo.descricao} -> movimento #{mov.id}"
                        + (f" ({'; '.join(avisos)})" if avisos else "")
                    )
                    ligados += 1

            if not aplicar:
                transaction.set_rollback(True)

        resumo = f"{ligados} títulos ligados ao caixa, {sem_movimento} para verificar à mão."
        if aplicar:
            self.stdout.write(self.style.SUCCESS(resumo))
        else:
            self.stdout.write(resumo + " Nada foi gravado; rode de novo com --aplicar.")

    # Movimento da quitação que aponta para um título apagado (ex.: lançamento refeito depois de quitado):
    # aceita só se houver exatamente um com o mesmo valor ainda sem título
    def movimentos_orfaos(self, modelo, tipo, origem, titulo):
        existentes = modelo.objects.values_list("id", flat=True)
        ligados = modelo.objects.exclude(caixa_movimento__isnull=True).values_list("caixa_movimento_id", flat=True)
        return list(CaixaMovimento.objects.filter(
            origem=origem, referencia_tipo=tipo, valor=titulo.valor_pago
        ).exclude(referencia_id__in=existentes).exclude(id__in=ligados))
