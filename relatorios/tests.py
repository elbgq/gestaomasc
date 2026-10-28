from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
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
        self.assertEqual(dre["receitas_financeiras"], Decimal("0"))  # aluguel não é receita financeira
        self.assertEqual(dre["resultado_antes_ir"], Decimal("50.00"))

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
        self.assertEqual(dre["receitas_financeiras"], Decimal("10.00"))
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
        self.assertEqual(dre["despesas_financeiras"], Decimal("5.50"))  # 3 + 1 pagos + 1,50 concedido
        self.assertEqual(dre["receitas_financeiras"], Decimal("2.50"))  # 2 recebidos + 0,50 obtido

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


class JurosMultasRelatorioTests(TestCase):
    # Relatório de origem das linhas de juros, multas e descontos do DRE
    def setUp(self):
        from django.contrib.auth import get_user_model
        from financeiro.models import FinanceiroPagar, FinanceiroReceber
        self.client.force_login(get_user_model().objects.create_superuser("teste", password="teste"))
        self.hoje = timezone.localdate()
        self.fornecedor = Contato.objects.create(nome="Fornecedor X", tipo="FORNECEDOR")
        self.cliente = Contato.objects.create(nome="Cliente Y", tipo="CLIENTE")
        despesa = FinanceiroCategoria.objects.create(nome="Compras", tipo="D")
        receita = FinanceiroCategoria.objects.create(nome="Vendas", tipo="R")
        comum = dict(data_lancamento=self.hoje, data_vencimento=self.hoje, status="pago", data_pagamento=self.hoje)
        self.pago = FinanceiroPagar.objects.create(
            contato=self.fornecedor, descricao="Boleto atrasado", valor=Decimal("100.00"), valor_pago=Decimal("100.00"),
            categoria=despesa, origem="COMPRA", valor_juros=Decimal("3.00"), valor_multa=Decimal("2.00"),
            valor_desconto=Decimal("0.50"), **comum)
        # Quitação sem encargos não aparece
        FinanceiroPagar.objects.create(contato=self.fornecedor, descricao="Em dia", valor=Decimal("50.00"),
                                       valor_pago=Decimal("50.00"), categoria=despesa, origem="MANUAL", **comum)
        self.recebido = FinanceiroReceber.objects.create(
            cliente=self.cliente, descricao="Parcela cliente", valor=Decimal("80.00"), valor_pago=Decimal("80.00"),
            categoria=receita, origem="VENDA", valor_juros=Decimal("1.60"), valor_desconto=Decimal("4.00"), **comum)
        juros = FinanceiroCategoria.objects.create(nome="Juros Recebidos", tipo="R", grupo_dre="RECEITAS_FINANCEIRAS")
        FinanceiroLancamento.objects.create(data=self.hoje, categoria=juros, descricao="Juros da aplicação",
                                            valor=Decimal("7.00"))

    def test_totais_batem_com_as_linhas_do_dre(self):
        from relatorios.services.juros_service import juros_multas_descontos
        dados = juros_multas_descontos(self.hoje, self.hoje)
        dre = dre_por_periodo(self.hoje, self.hoje)
        self.assertEqual(len(dados["pagar"]["linhas"]), 1)
        self.assertEqual(dados["pagar"]["totais"]["juros_multa"], dre["juros_multas_pagos"])
        self.assertEqual(dados["pagar"]["totais"]["desconto"], dre["descontos_obtidos"])
        self.assertEqual(dados["receber"]["totais"]["juros_multa"], dre["juros_multas_recebidos"])
        self.assertEqual(dados["receber"]["totais"]["desconto"], dre["descontos_concedidos"])
        self.assertEqual(dados["receber"]["totais_lancados"]["total"], dre["receitas_financeiras_lancadas"])
        self.assertEqual(dados["pagar"]["totais_lancados"]["total"], dre["despesas_financeiras_lancadas"])
        self.assertEqual(dre["receitas_financeiras"], Decimal("9.10"))  # 1,60 + 0,50 + 7,00

    def test_estorno_tira_o_titulo_do_relatorio(self):
        from financeiro.models import Caixa
        from financeiro.services import estornar_quitacao
        from relatorios.services.juros_service import juros_multas_descontos
        Caixa.objects.create(nome="Caixa Principal", saldo_inicial=Decimal("200.00"))
        estornar_quitacao(self.pago)
        self.assertEqual(juros_multas_descontos(self.hoje, self.hoje)["pagar"]["linhas"], [])

    def test_tela_lista_os_titulos_com_links(self):
        url = reverse("relatorios:juros_multas")
        resp = self.client.get(url, {"data_inicio": self.hoje, "data_fim": self.hoje})
        self.assertContains(resp, "Boleto atrasado")
        self.assertContains(resp, "Parcela cliente")
        self.assertContains(resp, "Juros da aplicação")
        self.assertNotContains(resp, "Em dia")
        self.assertContains(resp, reverse("financeiro:titulo_detalhe", args=["D", self.pago.id]))

        so_recebidas = self.client.get(url, {"data_inicio": self.hoje, "data_fim": self.hoje, "tipo": "receber"})
        self.assertNotContains(so_recebidas, "Boleto atrasado")
        self.assertContains(so_recebidas, "Parcela cliente")
        self.assertContains(so_recebidas, "Juros da aplicação")  # lançamento entra na tabela de recebidas
        self.assertContains(so_recebidas, "Lançamento")

    def test_exporta_csv(self):
        resp = self.client.get(reverse("relatorios:juros_multas"),
                               {"data_inicio": self.hoje, "data_fim": self.hoje, "formato": "csv"})
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        texto = resp.content.decode("utf-8-sig")
        self.assertIn("Boleto atrasado", texto)
        self.assertIn("3,00;2,00;0,50;104,50", texto)

    def test_dre_linka_para_o_relatorio(self):
        resp = self.client.get(reverse("relatorios:dre"), {"data_inicio": self.hoje, "data_fim": self.hoje})
        self.assertContains(resp, reverse("relatorios:juros_multas") + "?data_inicio=")
        self.assertContains(resp, "tipo=pagar")

    def test_conta_manual_de_multa_vai_na_coluna_multa_das_contas_pagas(self):
        from financeiro.models import FinanceiroPagar
        from relatorios.services.juros_service import juros_multas_descontos
        multas = FinanceiroCategoria.objects.create(nome="Multas Pagas", tipo="D", grupo_dre="DESPESAS_FINANCEIRAS")
        FinanceiroPagar.objects.create(contato=self.fornecedor, descricao="Multa de trânsito", valor=Decimal("130.00"),
                                       categoria=multas, origem="MANUAL", data_lancamento=self.hoje,
                                       data_vencimento=self.hoje)
        pagar = juros_multas_descontos(self.hoje, self.hoje)["pagar"]
        linha = pagar["linhas"][-1]
        self.assertEqual((linha["origem"], linha["multa"], linha["juros"]), ("Manual", Decimal("130.00"), Decimal("0.00")))
        self.assertEqual(pagar["totais_lancados"]["total"], dre_por_periodo(self.hoje, self.hoje)["despesas_financeiras_lancadas"])
        self.assertEqual(pagar["totais_geral"]["multa"], Decimal("132.00"))


class PainelTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        from cadastros.models import Produto
        from core.tests import usuario
        cache.clear()
        self.usuario = usuario
        self.hoje = timezone.localdate()
        self.cliente = Contato.objects.create(nome="Cliente", tipo="CLIENTE")
        self.servico = Servico.objects.create(codsv="S1", descricao="Instalação", unidade="UN")
        self.produto = Produto.objects.create(codor="P1", descricao="Cabo", unidade="UN", estoque_minimo=5)

    def venda(self, quando, valor="100.00", status="finalizada", forma="pix"):
        venda = Venda.objects.create(cliente=self.cliente, status=status, forma_pagamento=forma,
                                     data_emissao=timezone.make_aware(datetime.combine(quando, time(10, 0))))
        VendaItem.objects.create(venda=venda, servico=self.servico, quantidade=1, preco_unitario=Decimal(valor))
        return venda

    def test_periodos_e_comparacao(self):
        from relatorios.services.painel import periodo
        p = periodo("mes", date(2026, 3, 31))
        self.assertEqual((p["ini"], p["fim"], p["ini_ant"], p["fim_ant"]),
                         (date(2026, 3, 1), date(2026, 3, 31), date(2026, 2, 1), date(2026, 2, 28)))
        p = periodo("mes_anterior", date(2026, 1, 15))
        self.assertEqual((p["ini"], p["fim"], p["ini_ant"], p["fim_ant"]),
                         (date(2025, 12, 1), date(2025, 12, 31), date(2025, 11, 1), date(2025, 11, 30)))
        p = periodo("7dias", date(2026, 3, 10))
        self.assertEqual((p["ini"], p["ini_ant"], p["fim_ant"]), (date(2026, 3, 4), date(2026, 2, 25), date(2026, 3, 3)))
        self.assertEqual(periodo("qualquer", date(2026, 3, 10))["codigo"], "mes")

    def test_bloco_vendas(self):
        from datetime import timedelta
        from relatorios.services.painel import bloco_vendas, periodo
        self.venda(self.hoje, "300.00")
        self.venda(self.hoje, "100.00", forma="dinheiro")
        self.venda(self.hoje, "999.00", status="rascunho")
        self.venda(self.hoje - timedelta(days=1), "200.00")  # entra só na comparação de "hoje"
        dados = bloco_vendas(periodo("hoje", self.hoje), ver_custos=False)
        self.assertEqual((dados["faturamento"], dados["qtd"], dados["ticket"]), (Decimal("400.00"), 2, Decimal("200.00")))
        self.assertEqual(dados["faturamento_var"], Decimal("100.0"))
        self.assertEqual(dados["rascunhos"], 1)
        self.assertEqual(dados["servicos"], Decimal("400.00"))
        self.assertEqual([f["nome"] for f in dados["formas"]], ["PIX", "Dinheiro"])
        self.assertEqual(dados["top_itens"][0], {"nome": "Instalação", "total": Decimal("400.00")})
        self.assertNotIn("margem", dados)  # sem permissão de custo, sem margem
        self.assertEqual(len(dados["serie"]["rotulos"]), 7)  # "hoje" mostra a semana no gráfico
        self.assertEqual(dados["serie"]["atual"][-2:], [200.0, 400.0])

    def test_bloco_estoque(self):
        from datetime import timedelta
        from cadastros.models import Produto
        from comercial.models import MovimentacaoEstoque
        from relatorios.services.painel import bloco_estoque, periodo
        parado = Produto.objects.create(codor="P2", descricao="Disjuntor", unidade="UN")
        MovimentacaoEstoque.objects.create(produto=self.produto, tipo="ENTRADA", quantidade=2,
                                           preco=Decimal("10.00"), origem="AJUSTE")
        mov = MovimentacaoEstoque.objects.create(produto=parado, tipo="ENTRADA", quantidade=4,
                                                 preco=Decimal("25.00"), origem="AJUSTE")
        MovimentacaoEstoque.objects.filter(pk=mov.pk).update(data=timezone.now() - timedelta(days=120))
        dados = bloco_estoque(periodo("mes", self.hoje), self.hoje, ver_custos=True)
        self.assertEqual(dados["abaixo_qtd"], 1)  # Cabo: saldo 2, mínimo 5
        self.assertEqual(dados["abaixo"][0]["produto"], self.produto)
        self.assertEqual(dados["valor"], Decimal("120.00"))
        self.assertEqual([p["produto"] for p in dados["parados"]], [parado])
        self.assertEqual(dados["parados_valor"], Decimal("100.00"))
        self.assertNotIn("valor", bloco_estoque(periodo("mes", self.hoje), self.hoje, ver_custos=False))

    def test_cada_perfil_ve_os_seus_blocos(self):
        from django.urls import reverse
        self.venda(self.hoje)
        casos = {
            "Administrador": {"financeiro", "vendas", "estoque", "clientes"},
            "Gerente": {"vendas", "estoque"},
            "Financeiro": {"financeiro"},
            "Compras/Estoque": {"estoque"},
        }
        for grupo, esperado in casos.items():
            self.client.force_login(self.usuario(grupo.replace("/", "_"), grupo))
            self.assertRedirects(self.client.get(reverse("home")), reverse("relatorios:painel"))
            resp = self.client.get(reverse("relatorios:painel"))
            self.assertEqual(resp.status_code, 200, grupo)
            self.assertEqual({b for b in ("financeiro", "vendas", "estoque", "clientes") if b in resp.context}, esperado, grupo)
        # Margem só para quem vê custo
        self.client.force_login(self.usuario("gerente2", "Gerente"))
        self.assertContains(self.client.get(reverse("relatorios:painel")), "Margem bruta")
        self.client.force_login(self.usuario("fin2", "Financeiro"))
        self.assertNotContains(self.client.get(reverse("relatorios:painel")), "Margem bruta")

    def test_vendedor_nao_tem_painel(self):
        from django.urls import reverse
        self.client.force_login(self.usuario("vendedor", "Vendedor"))
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("relatorios:painel")).status_code, 403)

    def test_cache_e_atualizar(self):
        from django.urls import reverse
        self.client.force_login(self.usuario("adm", "Administrador"))
        self.venda(self.hoje, "100.00")
        url = reverse("relatorios:painel") + "?periodo=hoje"
        self.assertEqual(self.client.get(url).context["vendas"]["faturamento"], Decimal("100.00"))
        self.venda(self.hoje, "50.00")
        self.assertEqual(self.client.get(url).context["vendas"]["faturamento"], Decimal("100.00"))  # ainda no cache
        self.assertEqual(self.client.get(url + "&atualizar=1").context["vendas"]["faturamento"], Decimal("150.00"))

    def test_fluxo_projetado(self):
        from datetime import timedelta
        from financeiro.models import Caixa, FinanceiroPagar, FinanceiroReceber
        from relatorios.services.painel import bloco_financeiro
        Caixa.objects.create(nome="Caixa Principal", saldo_inicial=Decimal("100.00"))
        despesa = FinanceiroCategoria.objects.create(nome="Despesas", tipo="D")

        def titulo(modelo, dias, valor, **extra):
            pessoa = {"cliente": self.cliente} if modelo is FinanceiroReceber else {"contato": self.cliente, "categoria": despesa}
            return modelo.objects.create(data_lancamento=self.hoje, data_vencimento=self.hoje + timedelta(days=dias),
                                         descricao="T", valor=Decimal(valor), origem="MANUAL", **pessoa, **extra)

        titulo(FinanceiroReceber, 10, "50.00")
        titulo(FinanceiroPagar, 20, "200.00")
        titulo(FinanceiroReceber, 45, "300.00")
        titulo(FinanceiroPagar, -3, "999.00")               # vencido: fica fora da projeção
        titulo(FinanceiroPagar, 5, "999.00", status="pago")  # pago: fica fora
        fluxo = bloco_financeiro(self.hoje)["fluxo"]
        faixas = {f["dias"]: f for f in fluxo["faixas"]}
        self.assertEqual((faixas[30]["entradas"], faixas[30]["saidas"], faixas[30]["saldo"]),
                         (Decimal("50.00"), Decimal("200.00"), Decimal("-50.00")))
        self.assertEqual(faixas[90]["saldo"], Decimal("250.00"))
        self.assertEqual(fluxo["negativo_em"], self.hoje + timedelta(days=20))
        self.assertEqual(fluxo["menor"], {"saldo": Decimal("-50.00"), "data": self.hoje + timedelta(days=20)})
        self.assertEqual(len(fluxo["grafico"]["saldo"]), 91)

        # O alerta aparece na tela
        self.client.force_login(self.usuario("adm", "Administrador"))
        resp = self.client.get(reverse("relatorios:painel"))
        self.assertContains(resp, "Saldo previsto fica negativo em")

    def test_resultado_igual_a_dre(self):
        from relatorios.services.painel import bloco_resultado, periodo
        categoria = FinanceiroCategoria.objects.create(nome="Aluguel", tipo="D", grupo_dre="DESPESA_ADM")
        FinanceiroLancamento.objects.create(data=self.hoje, categoria=categoria, descricao="Aluguel", valor=Decimal("30.00"))
        self.venda(self.hoje, "100.00")
        per = periodo("hoje", self.hoje)
        dados, dre = bloco_resultado(per), dre_por_periodo(self.hoje, self.hoje)
        for campo in ("receita_liquida", "lucro_bruto", "despesas_operacionais", "lucro_liquido"):
            self.assertEqual(dados[campo], dre[campo], campo)
        self.assertEqual(dados["lucro_liquido"], Decimal("70.00"))
        self.assertEqual(dados["margem_liquida"], Decimal("70.0"))
        self.assertIsNone(dados["lucro_liquido_var"])  # ontem sem lucro: não compara

    def test_resultado_so_para_quem_ve_a_dre(self):
        self.venda(self.hoje)
        self.client.force_login(self.usuario("adm", "Administrador"))
        self.assertIn("resultado", self.client.get(reverse("relatorios:painel")).context)
        self.client.force_login(self.usuario("fin", "Financeiro"))
        self.assertIn("resultado", self.client.get(reverse("relatorios:painel")).context)
        self.client.force_login(self.usuario("ger", "Gerente"))
        self.assertNotIn("resultado", self.client.get(reverse("relatorios:painel")).context)  # sem bloco Financeiro

    def test_bloco_clientes(self):
        from datetime import timedelta
        from financeiro.models import FinanceiroReceber
        from relatorios.services.painel import bloco_clientes, periodo
        antigo = Contato.objects.create(nome="Antigo", tipo="CLIENTE", telefone="1199")
        novo = Contato.objects.create(nome="Novo", tipo="CLIENTE")
        fiel = self.cliente
        # Fiel comprou há 200 dias e de novo hoje (recompra); Novo comprou só hoje; Antigo parou há 120 dias
        self.venda(self.hoje - timedelta(days=200), "50.00")
        self.venda(self.hoje, "800.00")
        venda_novo = self.venda(self.hoje, "200.00")
        Venda.objects.filter(pk=venda_novo.pk).update(cliente=novo)
        venda_antigo = self.venda(self.hoje - timedelta(days=120), "500.00")
        Venda.objects.filter(pk=venda_antigo.pk).update(cliente=antigo)
        self.venda(self.hoje, "999.00", status="rascunho")  # rascunho não conta

        def receber(dias, valor, status="pendente", pago_em=None):
            return FinanceiroReceber.objects.create(
                data_lancamento=self.hoje, data_vencimento=self.hoje + timedelta(days=dias), cliente=antigo,
                descricao="T", valor=Decimal(valor), origem="MANUAL", status=status, data_pagamento=pago_em)

        receber(-10, "300.00")
        receber(20, "100.00")
        receber(-6, "50.00", status="pago", pago_em=self.hoje)    # pago com 6 dias de atraso
        receber(0, "50.00", status="pago", pago_em=self.hoje)     # pago em dia

        dados = bloco_clientes(periodo("hoje", self.hoje), self.hoje)
        self.assertEqual((dados["do_periodo"], dados["ativos"], dados["novos"]), (2, 2, 1))
        self.assertEqual((dados["recompra"], dados["recompra_pct"]), (1, Decimal("50.0")))
        self.assertEqual([p["cliente"] for p in dados["parados"]], [antigo])
        self.assertEqual([(l["cliente"], l["classe"]) for l in dados["abc"]], [(fiel, "A"), (novo, "B")])
        self.assertEqual(dados["abc"][0]["pct"], Decimal("80.0"))
        self.assertEqual((dados["inad_vencido"], dados["inad_aberto"], dados["inad_pct"]),
                         (Decimal("300.00"), Decimal("400.00"), Decimal("75.0")))
        self.assertEqual(dados["devedores"][0]["dias"], 10)
        self.assertEqual((dados["atraso_medio"], dados["em_dia_pct"]), (Decimal("3.0"), Decimal("50.0")))

        self.client.force_login(self.usuario("adm", "Administrador"))
        resp = self.client.get(reverse("relatorios:painel") + "?periodo=hoje")
        self.assertContains(resp, "Curva ABC do período")
        self.assertContains(resp, "1199")

    def test_meta_de_faturamento(self):
        from calendar import monthrange
        from comercial.models import MetaFaturamento
        from relatorios.services.painel import bloco_meta, periodo
        per = periodo("mes", self.hoje)
        self.assertIsNone(bloco_meta(per, self.hoje)["valor"])  # sem meta cadastrada
        MetaFaturamento.objects.create(mes=self.hoje, valor=Decimal("1000.00"))  # guarda o dia 1
        self.venda(self.hoje, "250.00")
        self.venda(self.hoje, "999.00", status="rascunho")
        dados = bloco_meta(per, self.hoje)
        dias_mes = monthrange(self.hoje.year, self.hoje.month)[1]
        restantes = dias_mes - self.hoje.day + 1
        self.assertEqual((dados["realizado"], dados["pct"], dados["falta"]), (Decimal("250.00"), Decimal("25.0"), Decimal("750.00")))
        self.assertEqual(dados["dias_restantes"], restantes)
        self.assertEqual(dados["por_dia"], (Decimal("750.00") / restantes).quantize(Decimal("0.01")))
        self.assertEqual(dados["projecao"], (Decimal("250.00") / self.hoje.day * dias_mes).quantize(Decimal("0.01")))
        # Mês anterior sem meta: o período "Mês anterior" mostra a dele
        self.assertIsNone(bloco_meta(periodo("mes_anterior", self.hoje), self.hoje)["valor"])

        self.client.force_login(self.usuario("adm", "Administrador"))
        self.assertContains(self.client.get(reverse("relatorios:painel")), "No ritmo de até hoje")

    def test_pos_venda_no_bloco_clientes(self):
        from datetime import timedelta
        from comercial.models import PosVenda
        from relatorios.services.painel import bloco_clientes, periodo
        PosVenda.objects.create(cliente=self.cliente, tipo="garantia", descricao="Disjuntor queimou",
                                retorno=self.hoje - timedelta(days=2))
        PosVenda.objects.create(cliente=self.cliente, tipo="contato", descricao="Ligar", retorno=self.hoje + timedelta(days=5))
        PosVenda.objects.create(cliente=self.cliente, tipo="reclamacao", descricao="Atraso", status="resolvido", solucao="Ok")
        pv = bloco_clientes(periodo("hoje", self.hoje), self.hoje)["pos_venda"]
        self.assertEqual((pv["abertos"], pv["atrasados"], pv["resolvidos_no_periodo"]), (2, 1, 1))
        self.assertEqual(pv["lista"][0].descricao, "Disjuntor queimou")  # o atrasado primeiro
        self.assertEqual(sum(t["qtd"] for t in pv["no_periodo"]), 3)

        self.client.force_login(self.usuario("adm", "Administrador"))
        self.assertContains(self.client.get(reverse("relatorios:painel")), "1 pós-venda(s) com retorno atrasado")
