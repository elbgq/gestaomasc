from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Contato
from financeiro.models import CaixaMovimento, FinanceiroCategoria, FinanceiroPagar, FinanceiroReceber


class TituloTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("teste", password="teste")
        self.client.force_login(user)
        self.contato = Contato.objects.create(nome="Fornecedor", tipo="FORNECEDOR")
        self.categoria = FinanceiroCategoria.objects.create(nome="Despesas", tipo="D")

    def titulo_pagar(self):
        return FinanceiroPagar.objects.create(
            data_lancamento=date.today(), data_vencimento=date.today(), contato=self.contato,
            descricao="Conta", valor=Decimal("30.00"), categoria=self.categoria, origem="MANUAL",
        )

    def test_pagar_titulo_duas_vezes_gera_um_movimento(self):
        titulo = self.titulo_pagar()
        url = reverse("financeiro:pagar_titulo", args=[titulo.id])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(CaixaMovimento.objects.count(), 1)

    def test_quitar_sem_caixa_principal_mostra_erro(self):
        titulo = self.titulo_pagar()
        resp = self.client.post(reverse("financeiro:titulo_confirmar_quitacao", args=["D", titulo.id]))
        self.assertEqual(resp.status_code, 302)
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, "pendente")

    def test_quitar_receber_sem_categoria(self):
        from financeiro.models import Caixa
        Caixa.objects.create(nome="Caixa Principal")
        titulo = FinanceiroReceber.objects.create(
            data_lancamento=date.today(), data_vencimento=date.today(), cliente=self.contato,
            descricao="Receita", valor=Decimal("10.00"), origem="MANUAL",
        )
        resp = self.client.post(reverse("financeiro:titulo_confirmar_quitacao", args=["R", titulo.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(CaixaMovimento.objects.get().referencia_tipo, "R")

    def test_detalhe_conta_da_compra(self):
        from comercial.models import Compra
        compra = Compra.objects.create(fornecedor=self.contato, data=date.today(), numero_nota="1")
        for i in range(2):
            conta = FinanceiroPagar.objects.create(
                data_lancamento=date.today(), data_vencimento=date.today(), contato=self.contato,
                descricao=f"Parcela {i}", valor=Decimal("10.00"), categoria=self.categoria,
                origem="COMPRA", compra=compra,
            )
        resp = self.client.get(reverse("financeiro:conta_detalhe", args=[conta.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["parcelas"]), 2)
