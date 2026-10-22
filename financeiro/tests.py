from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Contato
from financeiro.models import CaixaMovimento, FinanceiroCategoria, FinanceiroPagar, FinanceiroReceber


class TituloTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("teste", password="teste")
        self.client.force_login(user)
        self.contato = Contato.objects.create(nome="Fornecedor", tipo="FORNECEDOR")
        self.categoria = FinanceiroCategoria.objects.create(nome="Despesas", tipo="D")

    def titulo_pagar(self):
        return FinanceiroPagar.objects.create(
            data_lancamento=date.today(), data_vencimento=date.today(), contato=self.contato,
            descricao="Conta", valor=Decimal("30.00"), categoria=self.categoria, origem="MANUAL",
        )

    def test_pagar_titulo_duas_vezes_gera_um_movimento(self):
        from financeiro.models import Caixa
        Caixa.objects.create(nome="Caixa Principal", saldo_inicial=Decimal("100.00"))
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


class TelasFinanceiroTests(TestCase):
    setUp = TituloTests.setUp
    titulo_pagar = TituloTests.titulo_pagar

    def test_painel_financeiro_abre(self):
        FinanceiroReceber.objects.create(
            data_lancamento=date.today(), data_vencimento=date.today(), cliente=self.contato,
            descricao="Receita", valor=Decimal("10.00"), origem="MANUAL",
        )
        resp = self.client.get(reverse("financeiro:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["proximos"]), 1)

    def test_tela_de_pagar_titulo_abre(self):
        titulo = self.titulo_pagar()
        resp = self.client.get(reverse("financeiro:pagar_titulo", args=[titulo.id]))
        self.assertEqual(resp.status_code, 200)

    def test_tela_de_excluir_titulo_manual_abre(self):
        titulo = self.titulo_pagar()
        resp = self.client.get(reverse("financeiro:pagar_delete", args=[titulo.id]))
        self.assertContains(resp, "Conta")

    def test_caixa_aberto_fechar_sangria_e_reforco(self):
        from financeiro.models import Caixa, CaixaFechamento
        caixa = Caixa.objects.create(nome="Caixa Principal", saldo_inicial=Decimal("100.00"))
        self.client.post(reverse("financeiro:caixa_abrir", args=[caixa.id]), {"valor_abertura": "100"})
        self.assertEqual(self.client.get(reverse("financeiro:caixa_detalhe", args=[caixa.id])).status_code, 200)

        self.client.post(reverse("financeiro:caixa_reforco", args=[caixa.id]), {"valor": "50"})
        self.client.post(reverse("financeiro:caixa_sangria", args=[caixa.id]), {"valor": "30"})
        self.client.post(reverse("financeiro:caixa_sangria", args=[caixa.id]), {"valor": ""})
        self.client.post(reverse("financeiro:caixa_sangria", args=[caixa.id]), {"valor": "-5"})
        self.assertEqual(caixa.saldo_atual(), Decimal("120.00"))

        self.assertEqual(self.client.get(reverse("financeiro:caixa_fechar", args=[caixa.id])).status_code, 200)
        self.client.post(reverse("financeiro:caixa_fechar", args=[caixa.id]), {"valor_fechamento": "119.90"})
        self.assertEqual(CaixaFechamento.objects.get().diferenca, Decimal("-0.10"))

    def test_nova_e_editar_conta_a_receber_abrem(self):
        self.assertEqual(self.client.get(reverse("financeiro:receber_create")).status_code, 200)
        titulo = FinanceiroReceber.objects.create(
            data_lancamento=date.today(), data_vencimento=date.today(), cliente=self.contato,
            descricao="Receita", valor=Decimal("10.00"), origem="MANUAL",
        )
        self.assertEqual(self.client.get(reverse("financeiro:receber_update", args=[titulo.id])).status_code, 200)


class FluxoFinanceiroTests(TestCase):
    setUp_base = TituloTests.setUp
    titulo_pagar = TituloTests.titulo_pagar

    def setUp(self):
        from financeiro.models import Caixa
        self.setUp_base()
        self.caixa = Caixa.objects.create(nome="Caixa Principal", saldo_inicial=Decimal("100.00"))
        self.receita = FinanceiroCategoria.objects.create(nome="Receitas", tipo="R")

    def titulo_receber(self, origem="MANUAL"):
        return FinanceiroReceber.objects.create(
            data_lancamento=date.today(), data_vencimento=date.today(), cliente=self.contato,
            descricao="Receita", valor=Decimal("10.00"), origem=origem,
        )

    def test_as_duas_telas_de_quitacao_ligam_o_movimento_ao_titulo(self):
        a, b = self.titulo_pagar(), self.titulo_pagar()
        self.client.post(reverse("financeiro:pagar_titulo", args=[a.id]), {"data_pagamento": "2026-03-10"})
        self.client.post(reverse("financeiro:titulo_confirmar_quitacao", args=["D", b.id]))
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(a.caixa_movimento.data, date(2026, 3, 10))
        self.assertEqual(a.data_pagamento, date(2026, 3, 10))
        self.assertEqual(b.caixa_movimento.caixa, self.caixa)
        self.assertEqual(self.caixa.saldo_atual(), Decimal("40.00"))

    def test_pagar_sem_saldo_e_recusado(self):
        titulo = self.titulo_pagar()
        titulo.valor = Decimal("500.00"); titulo.save()
        self.client.post(reverse("financeiro:pagar_titulo", args=[titulo.id]))
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, "pendente")
        self.assertFalse(CaixaMovimento.objects.exists())

    def test_estorno_da_quitacao_volta_o_saldo_e_o_titulo(self):
        titulo = self.titulo_receber()
        self.client.post(reverse("financeiro:titulo_confirmar_quitacao", args=["R", titulo.id]))
        self.assertEqual(self.caixa.saldo_atual(), Decimal("110.00"))
        self.assertEqual(self.client.get(reverse("financeiro:titulo_estornar_quitacao", args=["R", titulo.id])).status_code, 200)
        self.client.post(reverse("financeiro:titulo_estornar_quitacao", args=["R", titulo.id]))
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, "pendente")
        self.assertEqual(titulo.valor_pago, Decimal("0.00"))
        self.assertIsNone(titulo.caixa_movimento)
        self.assertEqual(self.caixa.saldo_atual(), Decimal("100.00"))
        self.assertEqual(CaixaMovimento.objects.count(), 2)

    def test_titulo_pago_nao_e_editado_nem_excluido(self):
        pagar, receber = self.titulo_pagar(), self.titulo_receber()
        self.client.post(reverse("financeiro:pagar_titulo", args=[pagar.id]))
        self.client.post(reverse("financeiro:titulo_confirmar_quitacao", args=["R", receber.id]))

        self.client.post(reverse("financeiro:pagar_update", args=[pagar.id]), {"valor": "999"})
        self.client.post(reverse("financeiro:pagar_delete", args=[pagar.id]))
        self.client.post(reverse("financeiro:receber_update", args=[receber.id]), {"valor": "999"})
        self.client.post(reverse("financeiro:receber_delete", args=[receber.id]))

        pagar.refresh_from_db(); receber.refresh_from_db()
        self.assertEqual((pagar.valor, receber.valor), (Decimal("30.00"), Decimal("10.00")))

    def test_conta_a_receber_de_venda_nao_e_excluida(self):
        titulo = self.titulo_receber(origem="VENDA")
        self.client.post(reverse("financeiro:receber_delete", args=[titulo.id]))
        self.assertTrue(FinanceiroReceber.objects.filter(id=titulo.id).exists())
        # e só o vencimento pode ser alterado
        resp = self.client.get(reverse("financeiro:receber_update", args=[titulo.id]))
        self.assertEqual(list(resp.context["form"].fields), ["data_vencimento"])

    def dados_lancamento(self, categoria, valor="20.00"):
        return {"data": "2026-03-01", "contato": self.contato.id, "descricao": "Luz",
                "valor": valor, "categoria": categoria.id, "observacao": ""}

    def test_lancamento_cria_troca_e_exclui_o_titulo(self):
        from financeiro.models import FinanceiroLancamento
        self.client.post(reverse("financeiro:lancamento_create"), self.dados_lancamento(self.categoria))
        lanc = FinanceiroLancamento.objects.get()
        self.assertEqual(FinanceiroPagar.objects.get().valor, Decimal("20.00"))

        # Trocar despesa por receita troca o título
        self.client.post(reverse("financeiro:lancamento_update", args=[lanc.id]), self.dados_lancamento(self.receita))
        self.assertFalse(FinanceiroPagar.objects.exists())
        self.assertEqual(FinanceiroReceber.objects.get().cliente, self.contato)

        self.client.post(reverse("financeiro:lancamento_delete", args=[lanc.id]))
        self.assertFalse(FinanceiroLancamento.objects.exists())
        self.assertFalse(FinanceiroReceber.objects.exists())

    def test_lancamento_com_titulo_pago_nao_e_alterado(self):
        from financeiro.models import FinanceiroLancamento
        self.client.post(reverse("financeiro:lancamento_create"), self.dados_lancamento(self.categoria))
        lanc = FinanceiroLancamento.objects.get()
        self.client.post(reverse("financeiro:pagar_titulo", args=[FinanceiroPagar.objects.get().id]))

        self.client.post(reverse("financeiro:lancamento_update", args=[lanc.id]), self.dados_lancamento(self.categoria, "99"))
        self.client.post(reverse("financeiro:lancamento_delete", args=[lanc.id]))
        lanc.refresh_from_db()
        self.assertEqual(lanc.valor, Decimal("20.00"))
        self.assertEqual(FinanceiroPagar.objects.get().valor, Decimal("20.00"))

    def test_caixa_nao_abre_duas_vezes(self):
        from financeiro.models import CaixaAbertura
        url = reverse("financeiro:caixa_abrir", args=[self.caixa.id])
        self.client.post(url, {"valor_abertura": "100"})
        self.client.post(url, {"valor_abertura": "100"})
        self.assertEqual(CaixaAbertura.objects.count(), 1)

    def test_movimento_manual_fica_no_caixa(self):
        resp = self.client.post(reverse("financeiro:caixa_create"), {
            "caixa": self.caixa.id, "data": "2026-03-01", "descricao": "Troco", "tipo": "E", "valor": "5.00",
        })
        self.assertRedirects(resp, reverse("financeiro:caixa_detalhe", args=[self.caixa.id]))
        mov = CaixaMovimento.objects.get()
        self.assertEqual((mov.caixa, mov.origem), (self.caixa, "MANUAL"))
        self.client.post(reverse("financeiro:caixa_create"), {
            "caixa": self.caixa.id, "data": "2026-03-01", "descricao": "Negativo", "tipo": "E", "valor": "-5",
        })
        self.assertEqual(CaixaMovimento.objects.count(), 1)

    def test_painel_e_historico_usam_o_saldo_do_caixa(self):
        self.client.post(reverse("financeiro:caixa_reforco", args=[self.caixa.id]), {"valor": "50"})
        painel = self.client.get(reverse("financeiro:dashboard"))
        historico = self.client.get(reverse("financeiro:caixa_historico"))
        self.assertEqual(painel.context["saldo_atual"], Decimal("150.00"))
        self.assertEqual(historico.context["saldo_atual"], Decimal("150.00"))

    def test_grafico_tem_seis_meses_seguidos(self):
        from unittest import mock
        with mock.patch("financeiro.views_caixa.timezone.localdate", return_value=date(2026, 3, 31)):
            resp = self.client.get(reverse("financeiro:dashboard"))
        self.assertEqual(resp.context["meses"],
                         [date(2025, m, 1).strftime("%b/%Y") for m in (10, 11, 12)] +
                         [date(2026, m, 1).strftime("%b/%Y") for m in (1, 2, 3)])

    def test_totais_de_contas_a_pagar_separam_pago_e_aberto(self):
        pago, aberto = self.titulo_pagar(), self.titulo_pagar()
        self.client.post(reverse("financeiro:pagar_titulo", args=[pago.id]))
        resp = self.client.get(reverse("financeiro:contas_pagar_lista"))
        self.assertEqual(resp.context["aberto_avulsas"], Decimal("30.00"))
        self.assertEqual(resp.context["pago_avulsas"], Decimal("30.00"))
        resp = self.client.get(reverse("financeiro:contas_pagar_lista") + "?vencimento=hoje")
        self.assertEqual([t.id for t in resp.context["page_obj_avulsas"]], [aberto.id])

    def test_vincular_quitacoes_antigas(self):
        from django.core.management import call_command
        titulo = self.titulo_pagar()
        titulo.status, titulo.valor_pago, titulo.data_pagamento = "pago", titulo.valor, date.today()
        titulo.save()
        mov = CaixaMovimento.objects.create(caixa=self.caixa, data=date.today(), descricao="x", valor=titulo.valor,
                                            tipo="S", origem="PAGAMENTO", referencia_id=titulo.id, referencia_tipo="D")
        call_command("vincular_quitacoes", stdout=open("/dev/null", "w"))
        titulo.refresh_from_db()
        self.assertIsNone(titulo.caixa_movimento)
        call_command("vincular_quitacoes", "--aplicar", stdout=open("/dev/null", "w"))
        titulo.refresh_from_db()
        self.assertEqual(titulo.caixa_movimento, mov)


class QuitacaoAcrescimosTests(TestCase):
    setUp = FluxoFinanceiroTests.setUp
    setUp_base = TituloTests.setUp
    titulo_pagar = TituloTests.titulo_pagar
    titulo_receber = FluxoFinanceiroTests.titulo_receber

    def quitar(self, tipo, titulo, **campos):
        dados = {"data_pagamento": "2026-03-10", **campos}
        return self.client.post(reverse("financeiro:titulo_confirmar_quitacao", args=[tipo, titulo.id]), dados)

    def test_juros_multa_e_desconto_entram_no_caixa(self):
        titulo = self.titulo_pagar()
        self.quitar("D", titulo, valor_quitado="30.00", valor_juros="1,50", valor_multa="0.60", valor_desconto="2.10")
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, "pago")
        self.assertEqual(titulo.valor_pago, Decimal("30.00"))
        self.assertEqual(titulo.caixa_movimento.valor, Decimal("30.00"))
        self.assertEqual(titulo.total_quitado(), Decimal("30.00"))
        self.assertEqual((titulo.valor_juros, titulo.valor_multa, titulo.valor_desconto),
                         (Decimal("1.50"), Decimal("0.60"), Decimal("2.10")))

        receber = self.titulo_receber()
        self.quitar("R", receber, valor_juros="2.00")
        receber.refresh_from_db()
        self.assertEqual(receber.caixa_movimento.valor, Decimal("12.00"))
        self.assertEqual(self.caixa.saldo_atual(), Decimal("82.00"))

    def test_pagamento_parcial_deixa_o_saldo_em_aberto(self):
        titulo = self.titulo_pagar()
        self.client.post(reverse("financeiro:pagar_titulo", args=[titulo.id]), {"valor_quitado": "10.00"})
        titulo.refresh_from_db()
        saldo = FinanceiroPagar.objects.exclude(id=titulo.id).get()
        self.assertEqual((titulo.valor, titulo.status), (Decimal("10.00"), "pago"))
        self.assertEqual((saldo.valor, saldo.status, saldo.descricao), (Decimal("20.00"), "pendente", "Conta (saldo)"))
        self.assertEqual(saldo.data_vencimento, titulo.data_vencimento)

        # Quitar o saldo em duas vezes não repete "(saldo)"
        self.quitar("D", saldo, valor_quitado="5.00")
        self.assertEqual(FinanceiroPagar.objects.filter(status="pendente").get().descricao, "Conta (saldo)")
        self.assertEqual(sum(t.valor for t in FinanceiroPagar.objects.all()), Decimal("30.00"))

    def test_valores_invalidos_sao_recusados(self):
        titulo = self.titulo_pagar()
        for campos in ({"valor_quitado": "31"}, {"valor_quitado": "0"}, {"valor_juros": "-1"},
                       {"valor_desconto": "30"}, {"valor_juros": "abc"}):
            self.quitar("D", titulo, **campos)
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, "pendente")
        self.assertFalse(CaixaMovimento.objects.exists())
        self.assertEqual(FinanceiroPagar.objects.count(), 1)

    def test_estorno_devolve_o_total_com_juros(self):
        titulo = self.titulo_pagar()
        self.quitar("D", titulo, valor_juros="5.00")
        self.assertEqual(self.caixa.saldo_atual(), Decimal("65.00"))
        self.client.post(reverse("financeiro:titulo_estornar_quitacao", args=["D", titulo.id]))
        titulo.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual(), Decimal("100.00"))
        self.assertEqual((titulo.status, titulo.valor_juros), ("pendente", Decimal("0.00")))

    def test_telas_de_quitacao_mostram_os_campos(self):
        titulo = self.titulo_pagar()
        for url in (reverse("financeiro:pagar_titulo", args=[titulo.id]),
                    reverse("financeiro:titulo_confirmar_quitacao", args=["D", titulo.id])):
            self.assertContains(self.client.get(url), 'name="valor_juros"')


class CategoriaSugeridaTests(TestCase):
    setUp = FluxoFinanceiroTests.setUp
    setUp_base = TituloTests.setUp
    titulo_pagar = TituloTests.titulo_pagar

    def sugestao(self, tipo=""):
        return self.client.get(reverse("financeiro:api_categoria_sugerida", args=[self.contato.id]) + f"?tipo={tipo}").json()

    def test_sugere_a_categoria_padrao_do_contato(self):
        energia = FinanceiroCategoria.objects.create(nome="Energia elétrica", tipo="D")
        self.contato.categoria_padrao = energia
        self.contato.save()
        self.assertEqual(self.sugestao("D"), {"contato": "Fornecedor", "categoria_id": energia.id,
                                              "categoria": "Energia elétrica", "origem": "padrao"})
        # Categoria padrão de despesa não é sugerida para uma receita
        self.assertIsNone(self.sugestao("R")["categoria_id"])

    def test_sem_padrao_sugere_a_ultima_usada(self):
        from financeiro.models import FinanceiroLancamento
        FinanceiroLancamento.objects.create(data=date(2026, 1, 5), categoria=self.categoria, contato=self.contato,
                                            descricao="x", valor=Decimal("1"))
        self.assertEqual(self.sugestao()["categoria_id"], self.categoria.id)
        self.assertEqual(self.sugestao()["origem"], "historico")

    def test_formularios_trazem_a_sugestao(self):
        from financeiro.models import FinanceiroLancamento
        self.assertContains(self.client.get(reverse("financeiro:lancamento_create")), "aviso-categoria")
        self.assertContains(self.client.get(reverse("financeiro:receber_create")), "aviso-categoria")

    def test_reclassifica_titulo_pago_sem_mexer_no_caixa(self):
        from financeiro.models import FinanceiroLancamento
        energia = FinanceiroCategoria.objects.create(nome="Energia elétrica", tipo="D")
        self.client.post(reverse("financeiro:lancamento_create"), {
            "data": "2026-03-01", "contato": self.contato.id, "descricao": "Luz", "valor": "20.00",
            "categoria": self.categoria.id, "observacao": ""})
        titulo = FinanceiroPagar.objects.get()
        self.client.post(reverse("financeiro:pagar_titulo", args=[titulo.id]))
        saldo = self.caixa.saldo_atual()

        url = reverse("financeiro:titulo_reclassificar", args=["D", titulo.id])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {"categoria": energia.id})

        titulo.refresh_from_db()
        lanc = FinanceiroLancamento.objects.get()
        self.assertEqual((titulo.categoria, lanc.categoria, titulo.status), (energia, energia, "pago"))
        self.assertIn('de "Despesas" para "Energia elétrica"', titulo.observacao)
        self.assertIn("teste", lanc.observacao)
        self.assertEqual(self.caixa.saldo_atual(), saldo)

    def test_reclassificar_recusa_categoria_de_outro_tipo(self):
        titulo = self.titulo_pagar()
        self.client.post(reverse("financeiro:titulo_reclassificar", args=["D", titulo.id]), {"categoria": self.receita.id})
        titulo.refresh_from_db()
        self.assertEqual(titulo.categoria, self.categoria)
