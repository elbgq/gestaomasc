from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from cadastros.models import Contato, Servico
from comercial.models import Venda, VendaItem
from financeiro.models import FinanceiroCategoria, FinanceiroLancamento
from relatorios.services.dre_service import dre_por_periodo
from relatorios.services.vendas_service import vendas_por_periodo


class DRETests(TestCase):
    def setUp(self):
        self.cliente = Contato.objects.create(nome="Cliente", tipo="CLIENTE")
        self.servico = Servico.objects.create(codsv="S1", descricao="Serviço", unidade="UN")
        self.hoje = timezone.localdate()

    def venda(self, status="finalizada", quando=None, valor="100.00"):
        quando = quando or timezone.make_aware(datetime.combine(self.hoje, time(15, 0)))
        venda = Venda.objects.create(cliente=self.cliente, data_emissao=quando, status=status)
        VendaItem.objects.create(venda=venda, servico=self.servico, quantidade=1, preco_unitario=Decimal(valor))
        return venda

    def test_receita_patrimonial_entra_no_dre(self):
        categoria = FinanceiroCategoria.objects.create(nome="Aluguel recebido", tipo="R", grupo_dre="RECEITA_PATRIMONIAL")
        FinanceiroLancamento.objects.create(data=self.hoje, categoria=categoria, descricao="Aluguel", valor=Decimal("50.00"))
        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(dre["outras_receitas"], Decimal("50.00"))

    def test_venda_em_rascunho_nao_entra_no_dre(self):
        self.venda(status="rascunho")
        self.venda(status="finalizada")
        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(dre["receita_bruta"], Decimal("100.00"))

    def test_venda_no_ultimo_dia_do_periodo_entra_no_dre(self):
        self.venda()
        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(dre["receita_bruta"], Decimal("100.00"))

    def test_relatorio_vendas_inclui_ultimo_dia_e_filtra_numero(self):
        venda = self.venda()
        self.assertEqual(vendas_por_periodo(self.hoje, self.hoje).count(), 1)
        self.assertEqual(vendas_por_periodo(numero_nota=str(venda.numero)).count(), 1)
