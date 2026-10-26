from django.test import TestCase
from django.urls import reverse
from cadastros.models import Contato, Produto

# Create your tests here.


class UnificarContatoTests(TestCase):
    def setUp(self):
        from datetime import date
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from comercial.models import Compra, ProdutoFornecedor
        from financeiro.models import FinanceiroCategoria, FinanceiroPagar
        self.client.force_login(get_user_model().objects.create_superuser("u", password="p"))
        self.manter = Contato.objects.create(nome="Fornecedor X", tipo="FORNECEDOR", documento="05624503000151")
        self.remover = Contato.objects.create(nome="Fornecedor X", tipo="FORNECEDOR", documento="09.567.345/0001-23",
                                              telefone="(51) 3793-1100")
        produto = Produto.objects.create(codor="P1", descricao="Produto", unidade="UN")
        Compra.objects.create(fornecedor=self.remover, data=date.today(), numero_nota="1")
        categoria = FinanceiroCategoria.objects.create(nome="Despesa", tipo="D")
        FinanceiroPagar.objects.create(contato=self.remover, descricao="t", valor=Decimal("10"), categoria=categoria,
                                       data_lancamento=date.today(), data_vencimento=date.today())
        ProdutoFornecedor.objects.create(fornecedor=self.manter, codigo_fornecedor="A1", produto=produto)
        ProdutoFornecedor.objects.create(fornecedor=self.remover, codigo_fornecedor="A1", produto=produto)
        ProdutoFornecedor.objects.create(fornecedor=self.remover, codigo_fornecedor="B2", produto=produto)

    def test_excluir_contato_com_registros_oferece_unificar(self):
        resp = self.client.post(reverse("cadastros:contato_delete", args=[self.remover.pk]))
        self.assertContains(resp, "não pode ser excluído")
        self.assertTrue(Contato.objects.filter(pk=self.remover.pk).exists())

    def test_unificar_passa_registros_e_apaga_o_duplicado(self):
        from comercial.models import Compra, ProdutoFornecedor
        from financeiro.models import FinanceiroPagar
        resp = self.client.post(reverse("cadastros:contato_unificar", args=[self.remover.pk]), {"manter": self.manter.pk})
        self.assertRedirects(resp, reverse("cadastros:contato_detail", args=[self.manter.pk]))
        self.assertFalse(Contato.objects.filter(pk=self.remover.pk).exists())
        self.assertEqual(Compra.objects.get().fornecedor, self.manter)
        self.assertEqual(FinanceiroPagar.objects.get().contato, self.manter)
        self.assertEqual(sorted(ProdutoFornecedor.objects.filter(fornecedor=self.manter)
                                .values_list("codigo_fornecedor", flat=True)), ["A1", "B2"])
        self.manter.refresh_from_db()
        self.assertEqual(self.manter.telefone, "(51) 3793-1100")
        self.assertEqual(self.manter.documento, "05624503000151")


class DocumentoContatoTests(TestCase):
    def test_formulario_grava_cnpj_com_mascara(self):
        from cadastros.forms import ContatoForm
        form = ContatoForm({"nome": "X", "tipo": "FORNECEDOR", "documento": "05624503000151"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().documento, "05.624.503/0001-51")

    def test_migracao_poe_mascara_nos_documentos_so_com_numeros(self):
        import importlib
        from django.apps import apps
        formatar = importlib.import_module("cadastros.migrations.0005_documento_com_mascara").formatar
        for doc in ("05624503000151", "12345678901", "09.567.345/0001-23", "123"):
            Contato.objects.create(nome=doc, tipo="OUTRO", documento=doc)
        formatar(apps, None)
        self.assertEqual(sorted(Contato.objects.values_list("documento", flat=True)),
                         sorted(["05.624.503/0001-51", "123.456.789-01", "09.567.345/0001-23", "123"]))


class PrecoVendaAutomaticoTests(TestCase):
    def setUp(self):
        from datetime import date
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from comercial.models import Compra, CompraItem
        self.Decimal = Decimal
        self.client.force_login(get_user_model().objects.create_superuser("u", password="p"))
        self.fornecedor = Contato.objects.create(nome="Fornecedor", tipo="FORNECEDOR")
        self.produto = Produto.objects.create(codor="P1", descricao="Produto", unidade="UN")

        def comprar(preco, quantidade=10):
            compra = Compra.objects.create(fornecedor=self.fornecedor, data=date.today(), numero_nota="1")
            CompraItem.objects.create(compra=compra, produto=self.produto, quantidade=quantidade,
                                      preco_unitario=Decimal(preco), total=0, status="vinculado")
            compra.atualizar_valor_total()
            return self.client.post(reverse("comercial:compras_finalizar_avista", args=[compra.id]), follow=True)
        self.comprar = comprar

    def recarregar(self):
        self.produto.refresh_from_db()
        return self.produto

    def test_compra_calcula_preco_com_markup_de_62(self):
        resp = self.comprar("10.00")
        self.assertEqual(self.recarregar().preco_venda, self.Decimal("16.20"))
        self.assertContains(resp, "Preço de venda atualizado pelo novo custo")

    def test_preco_acompanha_o_custo_medio(self):
        self.comprar("10.00")
        self.comprar("20.00")  # custo médio 15,00
        self.assertEqual(self.recarregar().preco_venda, self.Decimal("24.30"))

    def test_preco_manual_nao_muda_e_e_sinalizado(self):
        self.produto.preco_venda = self.Decimal("15.00")
        self.produto.preco_manual = True
        self.produto.save()
        resp = self.comprar("10.00")  # sugerido 16,20; 15,00 está 7,4% abaixo (tolerância 5%)
        produto = self.recarregar()
        self.assertEqual(produto.preco_venda, self.Decimal("15.00"))
        self.assertEqual(produto.situacao_preco(), "fora_sugerido")
        self.assertContains(resp, "Preço de venda para conferir em Revisão de preços")

    def test_preco_manual_dentro_da_tolerancia_nao_e_sinalizado(self):
        self.produto.preco_venda = self.Decimal("16.50")
        self.produto.preco_manual = True
        self.produto.save()
        self.comprar("10.00")
        self.assertIsNone(self.recarregar().situacao_preco())

    def test_preco_abaixo_do_custo(self):
        self.produto.preco_venda = self.Decimal("9.00")
        self.produto.preco_manual = True
        self.produto.save()
        self.comprar("10.00")
        self.assertEqual(self.recarregar().situacao_preco(), "abaixo_custo")
        resp = self.client.get(reverse("comercial:api_preco", args=["produto", self.produto.pk])).json()
        self.assertTrue(resp["abaixo_custo"])
        self.assertNotIn("custo", {k for k in resp if k != "abaixo_custo"})

    def dados_form(self, preco, manual=False):
        dados = {"codor": "P1", "descricao": "Produto", "unidade": "UN", "preco_venda": preco,
                 "marca": "", "ean": "", "ncm": "", "cest": ""}
        if manual:
            dados["preco_manual"] = "on"
        return dados

    def test_digitar_preco_diferente_do_sugerido_vira_manual(self):
        self.comprar("10.00")
        resp = self.client.post(reverse("cadastros:produto_update", args=[self.produto.pk]),
                                self.dados_form("18.00"), follow=True)
        produto = self.recarregar()
        self.assertEqual(produto.preco_venda, self.Decimal("18.00"))
        self.assertTrue(produto.preco_manual)
        self.assertContains(resp, "passou a ter preço manual")

    def test_voltar_ao_automatico_com_o_preco_sugerido(self):
        self.produto.preco_venda = self.Decimal("18.00")
        self.produto.preco_manual = True
        self.produto.save()
        self.comprar("10.00")
        self.client.post(reverse("cadastros:produto_update", args=[self.produto.pk]), self.dados_form("16.20"))
        self.assertFalse(self.recarregar().preco_manual)
        self.comprar("20.00")
        self.assertEqual(self.recarregar().preco_venda, self.Decimal("24.30"))

    def test_produto_novo_sem_custo_aceita_preco_digitado(self):
        self.client.post(reverse("cadastros:produto_create"),
                         {**self.dados_form("30.00"), "codor": "P2", "descricao": "Novo"})
        novo = Produto.objects.get(codor="P2")
        self.assertEqual(novo.preco_venda, self.Decimal("30.00"))
        self.assertFalse(novo.preco_manual)

    def test_revisao_aplica_o_sugerido_nos_marcados(self):
        self.produto.preco_venda = self.Decimal("15.00")
        self.produto.preco_manual = True
        self.produto.save()
        self.comprar("10.00")
        resp = self.client.get(reverse("cadastros:revisao_precos"))
        self.assertContains(resp, "fora do sugerido")
        self.client.post(reverse("cadastros:revisao_precos"), {"acao": "aplicar", "produtos": [self.produto.pk]})
        produto = self.recarregar()
        self.assertFalse(produto.preco_manual)
        self.assertEqual(produto.preco_venda, self.Decimal("16.20"))

    def test_mudar_markup_recalcula_so_os_automaticos(self):
        from cadastros.models import ConfiguracaoPreco
        self.comprar("10.00")
        manual = Produto.objects.create(codor="P2", descricao="Manual", unidade="UN",
                                        preco_venda=self.Decimal("50.00"), preco_manual=True)
        self.client.post(reverse("cadastros:revisao_precos"), {"acao": "config", "markup": "50", "tolerancia": "5"})
        self.assertEqual(ConfiguracaoPreco.atual().markup, self.Decimal("50"))
        self.assertEqual(self.recarregar().preco_venda, self.Decimal("15.00"))
        manual.refresh_from_db()
        self.assertEqual(manual.preco_venda, self.Decimal("50.00"))

    def test_recalculo_do_estoque_atualiza_o_preco(self):
        from comercial.models import Estoque, MovimentacaoEstoque
        self.comprar("10.00")
        # Uma entrada errada é apagada e o estoque é refeito (como no estorno)
        MovimentacaoEstoque.objects.create(produto=self.produto, tipo="ENTRADA", quantidade=10,
                                           preco=self.Decimal("30.00"), origem="AJUSTE")
        self.assertEqual(self.recarregar().preco_venda, self.Decimal("32.40"))  # custo médio 20,00
        MovimentacaoEstoque.objects.filter(origem="AJUSTE").delete()
        Estoque.objects.get(produto=self.produto).recalcular_preco_medio()
        self.assertEqual(self.recarregar().preco_venda, self.Decimal("16.20"))

    def test_csv_marca_preco_como_manual(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import tempfile
        from django.test import override_settings
        arquivo = SimpleUploadedFile("p.csv", "codor;descricao;unidade;preco;marca\nP9;Do CSV;UN;12,50;X\n".encode())
        with tempfile.TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta):
            self.client.post(reverse("cadastros:importar_produtos"), {"csv_file": arquivo})
        self.assertTrue(Produto.objects.get(codor="P9").preco_manual)


class PrecoVendaPermissoesTests(TestCase):
    def usuario(self, grupo):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group
        user = get_user_model().objects.create_user(grupo, password="x")
        user.groups.add(Group.objects.get(name=grupo))
        return user

    def test_gerente_acessa_revisao_e_vendedor_nao(self):
        self.client.force_login(self.usuario("Gerente"))
        self.assertEqual(self.client.get(reverse("cadastros:revisao_precos")).status_code, 200)
        self.client.force_login(self.usuario("Vendedor"))
        self.assertEqual(self.client.get(reverse("cadastros:revisao_precos")).status_code, 403)

    def test_vendedor_nao_ve_selo_de_custo(self):
        from decimal import Decimal
        from comercial.models import Estoque
        produto = Produto.objects.create(codor="P1", descricao="Produto", unidade="UN",
                                         preco_venda=Decimal("5.00"), preco_manual=True)
        Estoque.objects.create(produto=produto, quantidade=1, preco_medio=Decimal("10.00"))
        self.client.force_login(self.usuario("Vendedor"))
        html = self.client.get(reverse("cadastros:produto_list")).content.decode()
        self.assertIn("manual", html)
        self.assertNotIn("abaixo do custo", html)
        self.assertNotIn("Revisão de preços", html)
        html = self.client.get(reverse("cadastros:produto_detail", args=[produto.pk])).content.decode()
        self.assertNotIn("Custo médio", html)


class ClienteRapidoTests(TestCase):
    # Cadastro de cliente aberto pela tela de venda
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.create_superuser("u", password="p"))
        self.url = reverse("cadastros:contato_create_ajax")

    def test_cria_cliente_e_devolve_para_o_campo(self):
        resposta = self.client.post(self.url, {"nome": "Maria", "documento": "12345678909", "telefone": "", "email": ""})
        self.assertEqual(resposta.status_code, 200)
        cliente = Contato.objects.get(nome="Maria")
        self.assertEqual(cliente.tipo, "CLIENTE")
        self.assertEqual(cliente.documento, "123.456.789-09")
        self.assertEqual(resposta.json(), {"id": cliente.pk, "nome": "Maria"})

    def test_nome_obrigatorio(self):
        resposta = self.client.post(self.url, {"nome": "", "documento": ""})
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("nome", resposta.json()["erros"])
        self.assertFalse(Contato.objects.exists())

    def test_documento_repetido_oferece_o_cliente_existente(self):
        existente = Contato.objects.create(nome="João", tipo="CLIENTE", documento="123.456.789-09")
        resposta = self.client.post(self.url, {"nome": "João Silva", "documento": "12345678909"})
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json()["existente"], {"id": existente.pk, "nome": "João"})
        self.assertEqual(Contato.objects.count(), 1)

    def test_documento_de_fornecedor_nao_vira_cliente(self):
        Contato.objects.create(nome="Fornecedor", tipo="FORNECEDOR", documento="05.624.503/0001-51")
        resposta = self.client.post(self.url, {"nome": "Outro", "documento": "05624503000151"})
        self.assertEqual(resposta.status_code, 400)
        self.assertNotIn("existente", resposta.json())

    def test_so_aceita_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class EanNoCadastroTests(TestCase):
    # Código de barras visível na lista e no detalhe do produto
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.create_superuser("u", password="p"))

    def test_lista_e_detalhe_mostram_o_ean(self):
        produto = Produto.objects.create(codor="P1", descricao="Produto", unidade="UN", ean="7891234567895")
        self.assertContains(self.client.get(reverse("cadastros:produto_list")), "7891234567895")
        self.assertContains(self.client.get(reverse("cadastros:produto_detail", args=[produto.pk])), "7891234567895")

    def test_detalhe_avisa_sem_ean_e_mostra_o_da_nota(self):
        from comercial.models import ProdutoFornecedor
        produto = Produto.objects.create(codor="P2", descricao="Sem EAN", unidade="UN")
        fornecedor = Contato.objects.create(nome="Fornecedor", tipo="FORNECEDOR")
        ProdutoFornecedor.objects.create(fornecedor=fornecedor, codigo_fornecedor="A", ean="7890000000017", produto=produto)
        ProdutoFornecedor.objects.create(fornecedor=fornecedor, codigo_fornecedor="CX", ean="7890000000024",
                                         produto=produto, fator_conversao=12)
        html = self.client.get(reverse("cadastros:produto_detail", args=[produto.pk])).content.decode()
        self.assertIn("Sem código de barras", html)
        self.assertIn("7890000000017", html)
        self.assertNotIn("7890000000024", html)


class ReajusteServicosTests(TestCase):
    TEXTO = """
        TABELA DE PREÇOS MÉDIOS DE SERVIÇOS ELÉTRICOS - 2026
    ILUMINAÇÃO                         Preço MÍNIMO        Preço MÁXIMO       Preço MÉDIO
    INSTALAÇÃO DE TOMADA SIMPLES          R$ 45,00            R$ 70,00          R$ 58,00
    INSTALAÇÃO DE CÂMERAS 3 WIFI   (sem ponto elétrico )   R$ 410,00   R$ 450,00   R$ 43 0,00
    QUADROS DE DISTRIBUIÇÃO / PAINEL   Preço MÍNIMO        Preço MÁXIMO       Preço MÉDIO
    INTERFONE 2 CHAMADAS                  R$ 220,00           R$ 170,00         R$ 195,00
    DISJUNTOR TRIFÁSICO                   R$ 120,00           R$ 130,00         R$ 115,00
    CARREGADOR VEICULAR                   R$ 1.200,00         R$1800,00         R$1.500,00
    """

    def setUp(self):
        from decimal import Decimal
        from cadastros.models import Servico
        from cadastros.tabela_servicos import ler_texto_tabela
        self.linhas = ler_texto_tabela(self.TEXTO)
        self.tomada = Servico.objects.create(codsv="SV001", descricao="Instalação de tomada simples",
                                             unidade="UN", preco_servico=Decimal("45"))
        self.camera = Servico.objects.create(codsv="SV002", descricao="INSTALAÇÃO DE CÂMERAS 3 WIFI",
                                             unidade="UN", preco_servico=Decimal("360"))
        self.fora = Servico.objects.create(codsv="SV007", descricao="Serviço avulso", unidade="UN",
                                           preco_servico=Decimal("10"))

    def test_le_categorias_e_valores_mesmo_com_digitos_separados(self):
        from decimal import Decimal
        self.assertEqual(len(self.linhas), 5)
        self.assertEqual(self.linhas[0]["categoria"], "ILUMINAÇÃO")
        self.assertEqual(self.linhas[1]["descricao"], "INSTALAÇÃO DE CÂMERAS 3 WIFI (sem ponto elétrico )")
        self.assertEqual(self.linhas[1]["medio"], Decimal("430.00"))
        self.assertEqual(self.linhas[4]["categoria"], "QUADROS DE DISTRIBUIÇÃO / PAINEL")
        self.assertEqual(self.linhas[4]["maximo"], Decimal("1800.00"))

    def test_erro_da_tabela_usa_meio_da_faixa(self):
        from decimal import Decimal
        from cadastros.tabela_servicos import preco_da_linha
        self.assertEqual(preco_da_linha(self.linhas[0]), (Decimal("58.00"), ""))
        preco, aviso = preco_da_linha(self.linhas[3])  # médio 115 abaixo do mínimo 120
        self.assertEqual(preco, Decimal("125.00"))
        self.assertIn("R$ 115,00", aviso)
        preco, aviso = preco_da_linha(self.linhas[2])  # mínimo e máximo invertidos
        self.assertEqual(preco, Decimal("195.00"))
        self.assertIn("mínimo maior que o máximo", aviso)

    def test_previa_casa_por_descricao_e_sugere_parecido(self):
        from cadastros.tabela_servicos import montar_previa
        previa, sem_tabela = montar_previa(self.linhas)
        self.assertEqual(previa[0]["servico"], self.tomada)  # sem acento/maiúsculas
        self.assertEqual(previa[0]["situacao"], "alterar")
        self.assertEqual(previa[1]["situacao"], "vincular")
        self.assertEqual(previa[1]["sugestoes"], [self.camera])
        self.assertEqual(previa[2]["situacao"], "novo")
        self.assertEqual(sem_tabela, [self.fora])

    def test_aplicar_grava_preco_faixa_categoria_e_historico(self):
        from decimal import Decimal
        from cadastros.models import CategoriaServico, ReajusteServico, Servico
        from cadastros.tabela_servicos import aplicar_previa, montar_previa
        escolhas = {0: {"destino": self.tomada.pk}, 1: {"destino": self.camera.pk, "usar_descricao": True},
                    2: {"destino": "novo"}, 3: {"destino": "novo"}}
        resumo = aplicar_previa(self.linhas, escolhas, 2026)
        self.assertEqual(resumo["reajustados"], 2)
        self.assertEqual(resumo["criados"], ["SV008", "SV009"])
        self.assertEqual(CategoriaServico.objects.count(), 2)

        self.tomada.refresh_from_db()
        self.assertEqual(self.tomada.preco_servico, Decimal("58.00"))
        self.assertEqual((self.tomada.preco_minimo, self.tomada.preco_maximo), (Decimal("45"), Decimal("70")))
        self.assertEqual(self.tomada.categoria.nome, "ILUMINAÇÃO")
        self.assertEqual(self.tomada.ano_tabela, 2026)
        self.camera.refresh_from_db()
        self.assertEqual(self.camera.descricao, "INSTALAÇÃO DE CÂMERAS 3 WIFI (sem ponto elétrico )")

        interfone = Servico.objects.get(codsv="SV008")
        self.assertEqual((interfone.preco_minimo, interfone.preco_maximo), (Decimal("170"), Decimal("220")))
        self.assertEqual(ReajusteServico.objects.filter(servico=self.tomada).get().preco_anterior, Decimal("45"))

        # A mesma tabela de novo: nada muda e o vínculo vale pela descrição da tabela
        previa, _ = montar_previa(self.linhas)
        self.assertEqual([p["situacao"] for p in previa[:4]], ["igual"] * 4)

    def test_tela_le_pdf_mostra_previa_e_aplica_marcados(self):
        from unittest import mock
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(get_user_model().objects.create_superuser("adm", password="p"))
        url = reverse("cadastros:reajuste_servicos")
        with mock.patch("cadastros.views.ler_tabela_pdf", return_value=(self.linhas, 2026)):
            resp = self.client.post(url, {"acao": "ler", "tabela": SimpleUploadedFile("t.pdf", b"%PDF")})
        self.assertRedirects(resp, url + "?previa=1")
        resp = self.client.get(url + "?previa=1")
        self.assertContains(resp, "Vincular a SV002")
        self.assertContains(resp, "Serviço avulso")  # fora da tabela

        resp = self.client.post(url, {"acao": "aplicar", "aplicar": ["0"], "destino_0": self.tomada.pk})
        self.assertRedirects(resp, reverse("cadastros:servico_list"))
        self.tomada.refresh_from_db()
        self.camera.refresh_from_db()
        self.assertEqual(self.tomada.preco_servico, Decimal("58.00"))
        self.assertEqual(self.camera.preco_servico, Decimal("360"))  # não marcado

    def test_tela_exige_permissao(self):
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.create_user("vend", password="p"))
        resp = self.client.get(reverse("cadastros:reajuste_servicos"))
        self.assertEqual(resp.status_code, 403)
