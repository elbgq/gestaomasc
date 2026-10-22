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

    def titulo(self, modelo, categoria, quando, valor="40.00", origem="MANUAL", **extra):
        from financeiro.models import FinanceiroPagar
        contato = {"contato": self.cliente} if modelo is FinanceiroPagar else {"cliente": self.cliente}
        return modelo.objects.create(
            data_lancamento=quando, data_vencimento=quando, descricao="Título", valor=Decimal(valor),
            categoria=categoria, origem=origem, **contato, **extra,
        )

    def test_titulos_manuais_entram_pela_competencia(self):
        from datetime import timedelta
        from financeiro.models import FinanceiroPagar, FinanceiroReceber
        despesa = FinanceiroCategoria.objects.create(nome="Aluguel", tipo="D", grupo_dre="DESPESA_ADM")
        receita = FinanceiroCategoria.objects.create(nome="Juros", tipo="R", grupo_dre="RECEITAS_FINANCEIRAS")
        mes_passado = self.hoje - timedelta(days=40)

        # Competência do mês passado, paga hoje: fica no mês passado
        self.titulo(FinanceiroPagar, despesa, mes_passado, status="pago", data_pagamento=self.hoje)
        self.titulo(FinanceiroPagar, despesa, self.hoje, valor="25.00")
        self.titulo(FinanceiroPagar, despesa, self.hoje, valor="999", status="cancelado")
        self.titulo(FinanceiroPagar, despesa, self.hoje, valor="999", origem="COMPRA")
        self.titulo(FinanceiroReceber, receita, self.hoje, valor="10.00")
        self.titulo(FinanceiroReceber, receita, self.hoje, valor="999", origem="VENDA")

        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(dre["despesas_adm"], Decimal("25.00"))
        self.assertEqual(dre["outras_receitas"], Decimal("10.00"))
        self.assertEqual(dre_por_periodo(mes_passado, mes_passado)["despesas_adm"], Decimal("40.00"))

    def test_receita_bruta_de_lancamento_e_impostos_juntos(self):
        servico = FinanceiroCategoria.objects.create(nome="Serviços avulsos", tipo="R", grupo_dre="RECEITA_BRUTA")
        pis_cofins = FinanceiroCategoria.objects.create(nome="PIS e COFINS", tipo="D", grupo_dre="PIS_COFINS")
        ir = FinanceiroCategoria.objects.create(nome="IR e CSLL", tipo="D", grupo_dre="IRPJ_CSLL")
        for cat, valor in ((servico, "200.00"), (pis_cofins, "20.00"), (ir, "30.00")):
            FinanceiroLancamento.objects.create(data=self.hoje, categoria=cat, descricao="x", valor=Decimal(valor))
        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(dre["receita_bruta"], Decimal("200.00"))
        self.assertEqual(dre["deducoes"], Decimal("20.00"))
        self.assertEqual(dre["lucro_liquido"], Decimal("150.00"))

    def test_categoria_sem_grupo_aparece_como_fora_do_dre(self):
        categoria = FinanceiroCategoria.objects.create(nome="Diversos", tipo="D")
        FinanceiroLancamento.objects.create(data=self.hoje, categoria=categoria, descricao="x", valor=Decimal("7.00"))
        self.assertEqual(dre_por_periodo(self.hoje, self.hoje)["fora_do_dre"], [("Diversos", Decimal("7.00"))])

    def test_migracao_corrige_grupos_antigos(self):
        import importlib
        from django.apps import apps
        corrigir = importlib.import_module("financeiro.migrations.0018_corrigir_grupos_dre_antigos").corrigir
        nomes = {"ICMS a Recolher": "IMPOSTOS_VENDAS", "PIS_COFINS": "IMPOSTOS_LUCROS",
                 "IRPJ_CSSL": "IMPOSTOS_LUCROS", "Juros Recebidos": "RECEITAS_FIN", "Multas Pagas": "DESPESAS_FIN"}
        for nome, grupo in nomes.items():
            FinanceiroCategoria.objects.create(nome=nome, tipo="D", grupo_dre=grupo)
        corrigir(apps, None)
        self.assertEqual(dict(FinanceiroCategoria.objects.values_list("nome", "grupo_dre")), {
            "ICMS a Recolher": "ICMS", "PIS_COFINS": "PIS_COFINS", "IRPJ_CSSL": "IRPJ_CSLL",
            "Juros Recebidos": "RECEITAS_FINANCEIRAS", "Multas Pagas": "DESPESAS_FINANCEIRAS",
        })

    def test_juros_multa_e_desconto_entram_pela_data_da_quitacao(self):
        from financeiro.models import FinanceiroPagar, FinanceiroReceber
        compras = FinanceiroCategoria.objects.create(nome="Compras", tipo="D")
        vendas = FinanceiroCategoria.objects.create(nome="Receita de Vendas", tipo="R")
        self.titulo(FinanceiroPagar, compras, self.hoje, origem="COMPRA", status="pago", data_pagamento=self.hoje,
                    valor_pago=Decimal("40.00"), valor_juros=Decimal("3.00"), valor_multa=Decimal("1.00"),
                    valor_desconto=Decimal("0.50"))
        self.titulo(FinanceiroReceber, vendas, self.hoje, origem="VENDA", status="pago", data_pagamento=self.hoje,
                    valor_pago=Decimal("40.00"), valor_juros=Decimal("2.00"), valor_desconto=Decimal("1.50"))
        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(dre["outras_despesas"], Decimal("5.50"))  # 3 + 1 pagos + 1,50 concedido
        self.assertEqual(dre["outras_receitas"], Decimal("2.50"))  # 2 recebidos + 0,50 obtido

    def test_relatorio_vendas_inclui_ultimo_dia_e_filtra_numero(self):
        venda = self.venda()
        self.assertEqual(vendas_por_periodo(self.hoje, self.hoje).count(), 1)
        self.assertEqual(vendas_por_periodo(numero_nota=str(venda.numero)).count(), 1)

    def test_relatorio_vendas_ignora_rascunho_e_cancelada_e_soma_desconto_da_venda(self):
        from relatorios.services.vendas_service import resumo_totais
        venda = self.venda()
        VendaItem.objects.create(venda=venda, servico=self.servico, quantidade=2,
                                 preco_unitario=Decimal("10.00"), desconto=Decimal("5.00"))
        venda.desconto, venda.acrescimo = Decimal("12.00"), Decimal("2.00")
        venda.atualizar_total()
        self.venda(status="rascunho")
        self.venda(status="cancelada")

        itens = vendas_por_periodo(self.hoje, self.hoje)
        totais = resumo_totais(itens)
        self.assertEqual(itens.count(), 2)
        self.assertEqual(totais["total_itens"], Decimal("115.00"))  # 100 + (20 - 5)
        self.assertEqual(totais["total_geral"], Decimal("105.00"))  # 115 - 12 + 2
        self.assertEqual(Venda.objects.get(pk=venda.pk).total, Decimal("105.00"))

    def test_dre_desconto_e_acrescimo_da_venda(self):
        venda = self.venda()
        venda.desconto, venda.acrescimo = Decimal("10.00"), Decimal("3.00")
        venda.atualizar_total()
        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(dre["receita_bruta"], Decimal("103.00"))
        self.assertEqual(dre["descontos_vendas"], Decimal("10.00"))
        self.assertEqual(dre["receita_liquida"], venda.total)

    def test_custos_lancados_ficam_junto_do_cmv(self):
        csp = FinanceiroCategoria.objects.create(nome="CSP", tipo="D", grupo_dre="CUSTOS")
        FinanceiroLancamento.objects.create(data=self.hoje, categoria=csp, descricao="x", valor=Decimal("30.00"))
        self.venda()
        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(dre["custos_lancados"], Decimal("30.00"))
        self.assertEqual(dre["lucro_bruto"], Decimal("70.00"))
        self.assertEqual(dre["despesas_operacionais"], Decimal("0"))

    def test_migracao_move_cmv_e_csp_para_custos(self):
        import importlib
        from django.apps import apps
        mover = importlib.import_module("financeiro.migrations.0021_grupo_custos").mover_custos
        for nome in ("CMV", "CSP", "Comissões"):
            FinanceiroCategoria.objects.create(nome=nome, tipo="D", grupo_dre="DESPESA_VENDAS")
        mover(apps, None)
        self.assertEqual(dict(FinanceiroCategoria.objects.values_list("nome", "grupo_dre")),
                         {"CMV": "CUSTOS", "CSP": "CUSTOS", "Comissões": "DESPESA_VENDAS"})

    def test_filtro_recusa_data_inicial_depois_da_final(self):
        from relatorios.forms import FiltroDREForm, FiltroComprasForm
        for form_cls in (FiltroDREForm, FiltroComprasForm):
            form = form_cls({"data_inicio": "2026-10-20", "data_fim": "2026-10-01"})
            self.assertFalse(form.is_valid())


class RelatorioComprasCMVTests(TestCase):
    def setUp(self):
        from cadastros.models import Produto
        from comercial.models import Compra, CompraItem
        self.fornecedor = Contato.objects.create(nome="Fornecedor", tipo="FORNECEDOR")
        self.produto = Produto.objects.create(codor="P1", descricao="Produto 1", unidade="UN")
        self.hoje = timezone.localdate()
        for confirmada, nota in ((True, "123"), (False, "456")):
            compra = Compra.objects.create(fornecedor=self.fornecedor, data=self.hoje, numero_nota=nota,
                                           confirmada=confirmada)
            CompraItem.objects.create(
                compra=compra, produto=self.produto, quantidade=10, preco_unitario=Decimal("10.00"),
                valor_frete=Decimal("5.00"), valor_ipi=Decimal("2.00"), valor_desconto=Decimal("7.50"),
                total=0,
            )
            compra.atualizar_valor_total()

    def test_compras_soma_valor_da_nota_so_das_confirmadas(self):
        from comercial.models import Compra
        from relatorios.services.compras_service import compras_por_periodo, resumo_totais
        itens = compras_por_periodo(self.hoje, self.hoje)
        totais = resumo_totais(itens)
        self.assertEqual(itens.count(), 1)
        self.assertEqual(totais["total_produtos"], Decimal("100.00"))
        self.assertEqual(totais["total_geral"], Decimal("99.50"))
        self.assertEqual(totais["total_geral"], Compra.objects.get(numero_nota="123").valor_total)

    def test_numero_da_nota_como_gravado(self):
        from comercial.models import Compra
        self.assertEqual(Compra(numero_nota="IMPORTADA").numero_formatado, "IMPORTADA")
        self.assertEqual(Compra(numero_nota="525550").numero_formatado, "525550")
        self.assertEqual(Compra(numero_nota="").numero_formatado, "—")

    def test_filtro_de_fornecedor_aparece_e_lista_so_fornecedores(self):
        from django.contrib.auth.models import User
        Contato.objects.create(nome="Cliente", tipo="CLIENTE")
        User.objects.create_superuser("u", password="p")
        self.client.login(username="u", password="p")
        resposta = self.client.get("/relatorios/compras/por-periodo/")
        self.assertContains(resposta, 'name="fornecedor"')
        self.assertContains(resposta, ">Fornecedor<")
        self.assertNotContains(resposta, ">Cliente<")

    def test_cmv_inclui_ultimo_dia_e_so_vendas_finalizadas(self):
        from comercial.models import CMVItem
        from relatorios.services.cmv_service import cmv_por_periodo
        cliente = Contato.objects.create(nome="Cliente", tipo="CLIENTE")
        noite = timezone.make_aware(datetime.combine(self.hoje, time(22, 0)))
        for status in ("finalizada", "cancelada"):
            venda = Venda.objects.create(cliente=cliente, data_emissao=noite, status=status)
            item = VendaItem.objects.create(venda=venda, produto=self.produto, quantidade=1,
                                            preco_unitario=Decimal("20.00"))
            CMVItem.objects.create(venda=venda, item=item, produto=self.produto, quantidade=1,
                                   custo_medio=Decimal("9.95"), total_cmv=Decimal("9.95"), data=noite)
        self.assertEqual(cmv_por_periodo(self.hoje, self.hoje).count(), 1)


class MovimentacaoEstoqueTests(TestCase):
    def setUp(self):
        from cadastros.models import Produto
        from comercial.models import MovimentacaoEstoque
        self.produto = Produto.objects.create(codor="P1", descricao="Produto 1", unidade="UN")
        self.hoje = timezone.localdate()
        cliente = Contato.objects.create(nome="Cliente", tipo="CLIENTE")
        self.venda = Venda.objects.create(cliente=cliente, status="finalizada")
        MovimentacaoEstoque.objects.create(produto=self.produto, tipo="ENTRADA", quantidade=10,
                                           preco=Decimal("5.00"), origem="AJUSTE")
        MovimentacaoEstoque.objects.create(produto=self.produto, tipo="SAIDA", quantidade=3,
                                           origem="VENDA", referencia_id=self.venda.id)
        # Uma entrada antiga, antes do período
        antiga = MovimentacaoEstoque.objects.create(produto=self.produto, tipo="ENTRADA", quantidade=2,
                                                    preco=Decimal("5.00"), origem="AJUSTE")
        from datetime import timedelta
        MovimentacaoEstoque.objects.filter(pk=antiga.pk).update(data=timezone.now() - timedelta(days=40))

    def test_resumo_fecha_saldo_e_valoriza_saidas_pelo_custo_medio(self):
        from relatorios.services.estoque_service import movimentacoes_por_periodo, resumo_por_produto, totais
        movs = movimentacoes_por_periodo(self.hoje, self.hoje)
        self.assertEqual(len(movs), 2)
        saida = [m for m in movs if m.tipo == "SAIDA"][0]
        self.assertEqual(saida.venda, self.venda)
        self.assertEqual(saida.valor, Decimal("15.00"))
        linha = resumo_por_produto(self.hoje, self.hoje)[0]
        self.assertEqual((linha["saldo_inicial"], linha["entradas"], linha["saidas"], linha["saldo_final"]),
                         (Decimal("2"), Decimal("10"), Decimal("3"), Decimal("9")))
        self.assertEqual(totais(movs)["valor_entradas"], Decimal("50.00"))

    def test_filtro_por_tipo_e_tela(self):
        from django.contrib.auth.models import User
        from relatorios.services.estoque_service import movimentacoes_por_periodo
        self.assertEqual(len(movimentacoes_por_periodo(self.hoje, self.hoje, tipo="SAIDA")), 1)
        self.assertEqual(len(movimentacoes_por_periodo(self.hoje, self.hoje, origem="venda")), 1)
        User.objects.create_superuser("u", password="p")
        self.client.login(username="u", password="p")
        resp = self.client.get("/relatorios/estoque/movimentacoes/",
                               {"data_inicio": self.hoje.isoformat(), "data_fim": self.hoje.isoformat()})
        self.assertContains(resp, "Resumo por Produto")
        self.assertContains(resp, self.venda.numero_formatado)
