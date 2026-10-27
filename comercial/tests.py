import io
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Contato, Produto
from comercial.models import Compra, CompraItem, Estoque, MovimentacaoEstoque, Venda, VendaItem
from comercial.views.views_estoque import registrar_cmv
from comercial.views.views_vendas import registrar_financeiro_venda
from financeiro.models import FinanceiroPagar, FinanceiroReceber


class BaseComercialTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("teste", password="teste")
        self.client.force_login(user)
        self.fornecedor = Contato.objects.create(nome="Fornecedor", tipo="FORNECEDOR")
        self.cliente = Contato.objects.create(nome="Cliente", tipo="CLIENTE")
        self.produto = Produto.objects.create(codor="P1", descricao="Produto 1", unidade="UN")

    def estoque(self):
        return Estoque.objects.get(produto=self.produto)

    def criar_compra(self, quantidade=10, preco="5.00"):
        compra = Compra.objects.create(fornecedor=self.fornecedor, data=date.today(), numero_nota="1")
        CompraItem.objects.create(
            compra=compra, produto=self.produto, quantidade=quantidade,
            preco_unitario=Decimal(preco), total=0, status="vinculado",
        )
        compra.atualizar_valor_total()
        return compra

    def dar_entrada(self, quantidade=10, preco="5.00"):
        MovimentacaoEstoque.objects.create(
            produto=self.produto, tipo="ENTRADA", quantidade=quantidade,
            preco=Decimal(preco), origem="AJUSTE",
        )

    def criar_venda(self, quantidade=2, preco="20.00"):
        venda = Venda.objects.create(cliente=self.cliente)
        VendaItem.objects.create(
            venda=venda, produto=self.produto, quantidade=quantidade,
            preco_unitario=Decimal(preco),
        )
        return venda

    def post_editar_venda(self, venda, quantidade, continuar="0", desconto="0", acrescimo="0"):
        item = venda.itens.first()
        return self.client.post(reverse("comercial:venda_editar", args=[venda.id]), {
            "cliente": self.cliente.id,
            "data_emissao": date.today().isoformat(),
            "forma_pagamento": "avista",
            "desconto": desconto,
            "acrescimo": acrescimo,
            "continuar": continuar,
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "1",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-id": item.id,
            "itens-0-venda": venda.id,
            "itens-0-produto": self.produto.id,
            "itens-0-servico": "",
            "itens-0-quantidade": str(quantidade),
            "itens-0-preco_unitario": "20.00",
            "itens-0-desconto": "0",
        })


class CompraTests(BaseComercialTest):
    def test_finalizar_compra_avista_soma_estoque_uma_vez(self):
        compra = self.criar_compra(quantidade=10, preco="5.00")
        self.client.post(reverse("comercial:compras_finalizar_avista", args=[compra.id]))
        self.assertEqual(self.estoque().quantidade, Decimal("10"))
        self.assertEqual(self.estoque().preco_medio, Decimal("5.00"))

    def test_finalizar_compra_duas_vezes_nao_duplica(self):
        compra = self.criar_compra(quantidade=10)
        url = reverse("comercial:compras_finalizar_avista", args=[compra.id])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(self.estoque().quantidade, Decimal("10"))
        self.assertEqual(FinanceiroPagar.objects.count(), 1)

    def test_compra_parcelada_parcelas_somam_total(self):
        compra = self.criar_compra(quantidade=1, preco="100.00")
        self.client.post(reverse("comercial:compras_finalizar_parcelado", args=[compra.id]), {
            "parcelas": "3", "dias_entre_parcelas": "30",
        })
        total = sum(t.valor for t in FinanceiroPagar.objects.all())
        self.assertEqual(total, Decimal("100.00"))

    def test_titulos_da_compra_aparecem_no_detalhe(self):
        compra = self.criar_compra()
        self.client.post(reverse("comercial:compras_finalizar_avista", args=[compra.id]))
        resp = self.client.get(reverse("comercial:compra_detalhe", args=[compra.id]))
        self.assertEqual(len(resp.context["titulos"]), 1)
        self.assertEqual(len(resp.context["movimentacoes"]), 1)

    def test_confirmar_compra_parcelado_pelo_formulario(self):
        compra = self.criar_compra(quantidade=1, preco="90.00")
        resp = self.client.post(reverse("comercial:compras_confirmar", args=[compra.id]), {
            "forma_pagamento": "parcelado", "parcelas": "3", "dias_entre_parcelas": "30",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FinanceiroPagar.objects.count(), 3)

    def test_criar_compra_redireciona(self):
        resp = self.client.post(reverse("comercial:compra_criar"), {
            "fornecedor": self.fornecedor.id,
            "data": date.today().isoformat(),
            "numero_nota": "123",
            "acao": "salvar",
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-produto": self.produto.id,
            "itens-0-unidade": "UN",
            "itens-0-quantidade": "2",
            "itens-0-preco_unitario": "3.00",
            "itens-0-total": "6.00",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Compra.objects.count(), 1)

    def test_quantidade_fracionada_na_compra(self):
        compra = self.criar_compra(quantidade=Decimal("2.5"), preco="4.00")
        item = compra.itens.first()
        item.refresh_from_db()
        self.assertEqual(item.quantidade, Decimal("2.5"))
        self.assertEqual(compra.valor_total, Decimal("10.00"))

    def test_estoque_ajax_produto_inexistente(self):
        resp = self.client.get(reverse("comercial:ajax_estoque", args=[999]))
        self.assertEqual(resp.status_code, 404)


class VendaTests(BaseComercialTest):
    def test_finalizar_venda_avista(self):
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=2)
        resp = self.post_editar_venda(venda, 2)
        self.assertEqual(resp.status_code, 302)
        venda.refresh_from_db()
        self.assertEqual(venda.status, "finalizada")
        self.assertEqual(self.estoque().quantidade, Decimal("8"))
        self.assertEqual(FinanceiroReceber.objects.count(), 1)
        self.assertEqual(venda.cmv, Decimal("10.00"))

    def test_salvar_venda_finalizada_de_novo_nao_baixa_estoque_outra_vez(self):
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=2)
        self.post_editar_venda(venda, 2)
        self.post_editar_venda(venda, 2)
        self.assertEqual(self.estoque().quantidade, Decimal("8"))
        self.assertEqual(FinanceiroReceber.objects.count(), 1)

    def test_editar_quantidade_de_venda_finalizada(self):
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=2)
        self.post_editar_venda(venda, 2)
        self.post_editar_venda(venda, 3)
        self.assertEqual(self.estoque().quantidade, Decimal("7"))

    def test_linha_vazia_e_ignorada_ao_finalizar(self):
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=2)
        item = venda.itens.first()
        resp = self.client.post(reverse("comercial:venda_editar", args=[venda.id]), {
            "cliente": self.cliente.id,
            "data_emissao": date.today().isoformat(),
            "forma_pagamento": "avista",
            "desconto": "0", "acrescimo": "0", "continuar": "0",
            "itens-TOTAL_FORMS": "2", "itens-INITIAL_FORMS": "1",
            "itens-MIN_NUM_FORMS": "0", "itens-MAX_NUM_FORMS": "1000",
            "itens-0-id": item.id, "itens-0-venda": venda.id,
            "itens-0-produto": self.produto.id, "itens-0-servico": "",
            "itens-0-quantidade": "2", "itens-0-preco_unitario": "20.00", "itens-0-desconto": "0",
            # Linha extra mexida pelo usuário, mas sem produto nem serviço
            "itens-1-produto": "", "itens-1-servico": "",
            "itens-1-quantidade": "0", "itens-1-preco_unitario": "", "itens-1-desconto": "0,00",
        })
        self.assertEqual(resp.status_code, 302)
        venda.refresh_from_db()
        self.assertEqual(venda.status, "finalizada")
        self.assertEqual(venda.itens.count(), 1)

    def test_item_com_quantidade_zero_e_recusado(self):
        from comercial.forms import VendaItemForm
        self.dar_entrada(10)
        form = VendaItemForm(data={"produto": self.produto.id, "quantidade": "0", "preco_unitario": "20.00", "desconto": "0"})
        self.assertFalse(form.is_valid())

    def test_venda_com_parcela_recebida_nao_pode_ser_editada(self):
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=2)
        self.post_editar_venda(venda, 2)
        FinanceiroReceber.objects.update(valor_pago=Decimal("40.00"), status="pago")
        self.post_editar_venda(venda, 5)
        self.assertEqual(self.estoque().quantidade, Decimal("8"))

    def test_detalhe_mostra_parcelas(self):
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=2)
        self.client.post(reverse("comercial:venda_parcelamento", args=[venda.id]), {
            "parcelas": "2", "dias_entre_parcelas": "30",
        })
        resp = self.client.get(reverse("comercial:venda_detalhe", args=[venda.id]))
        self.assertEqual(len(resp.context["parcelas"]), 2)

    def test_parcelas_da_venda_somam_total(self):
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=1, preco="100.00")
        registrar_financeiro_venda(venda, parcelas=3, dias=30, data_inicial=date.today())
        total = sum(t.valor for t in FinanceiroReceber.objects.all())
        self.assertEqual(total, Decimal("100.00"))

    def test_registrar_cmv_duas_vezes_nao_duplica_saida(self):
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=2)
        registrar_cmv(venda)
        registrar_cmv(venda)
        self.assertEqual(self.estoque().quantidade, Decimal("8"))

    def test_estorno_de_venda_com_entrada_devolve_a_entrada_uma_vez(self):
        from financeiro.models import Caixa
        from comercial.views.views_vendas import estornar_venda
        caixa = Caixa.objects.create(nome="Caixa Principal", saldo_inicial=Decimal("100.00"))
        self.dar_entrada(10)
        venda = self.criar_venda(quantidade=1, preco="100.00")
        venda.entrada = Decimal("30.00")
        registrar_financeiro_venda(venda, parcelas=2, dias=30, data_inicial=date.today())
        self.assertEqual(caixa.saldo_atual(), Decimal("130.00"))
        estornar_venda(venda)
        self.assertEqual(caixa.saldo_atual(), Decimal("100.00"))
        self.assertFalse(FinanceiroReceber.objects.exists())

    def test_estorno_devolve_estoque_sem_alterar_custo(self):
        self.dar_entrada(10, preco="5.00")
        venda = self.criar_venda(quantidade=2)
        registrar_cmv(venda)
        from comercial.views.views_vendas import estornar_venda
        estornar_venda(venda)
        self.assertEqual(self.estoque().quantidade, Decimal("10"))
        self.assertEqual(self.estoque().preco_medio, Decimal("5.00"))
        self.assertFalse(FinanceiroReceber.objects.filter(
            content_type=ContentType.objects.get_for_model(Venda), object_id=venda.id,
        ).exists())


class FormularioVendaTests(BaseComercialTest):
    def test_lista_so_produtos_com_estoque(self):
        from comercial.forms import VendaItemForm
        sem_estoque = Produto.objects.create(codor="P2", descricao="Sem estoque", unidade="UN")
        self.dar_entrada(5)
        opcoes = list(VendaItemForm().fields["produto"].queryset)
        self.assertIn(self.produto, opcoes)
        self.assertNotIn(sem_estoque, opcoes)

    def test_item_salvo_mantem_produto_sem_estoque(self):
        from comercial.forms import VendaItemForm
        self.dar_entrada(2)
        venda = self.criar_venda(quantidade=2)
        registrar_cmv(venda)
        self.assertEqual(self.estoque().quantidade, Decimal("0"))
        form = VendaItemForm(instance=venda.itens.first())
        self.assertIn(self.produto, list(form.fields["produto"].queryset))


class SignalsTests(BaseComercialTest):
    def test_produto_novo_tem_um_estoque(self):
        self.assertEqual(Estoque.objects.filter(produto=self.produto).count(), 1)


def nfe_xml(chave="35261012345678000199550010000012341000012345", numero="1234", cstat="100",
            dest="98765432000110", itens=None, protocolo=True, emit_cnpj="12345678000199",
            prod_extra="", imposto="", cobr="", vnf=None):
    itens = itens or [("A1", "7891234567895", "Parafuso 3mm", "CX", "2.0000", "50.0000000000")]
    dets = "".join(
        f'<det nItem="{n}"><prod><cProd>{c}</cProd><cEAN>{e}</cEAN><xProd>{d}</xProd>'
        f'<NCM>73181500</NCM><uCom>{u}</uCom><qCom>{q}</qCom><vUnCom>{v}</vUnCom>{prod_extra}</prod>'
        f'{imposto}</det>'
        for n, (c, e, d, u, q, v) in enumerate(itens, 1)
    )
    nfe = (
        f'<NFe><infNFe Id="NFe{chave}" versao="4.00"><ide><nNF>{numero}</nNF>'
        f'<dhEmi>2026-10-10T10:00:00-03:00</dhEmi><tpAmb>1</tpAmb></ide>'
        f'<emit><CNPJ>{emit_cnpj}</CNPJ><xNome>Distribuidora X</xNome></emit>'
        f'<dest><CNPJ>{dest}</CNPJ></dest>{dets}'
        + (f'<total><ICMSTot><vNF>{vnf}</vNF></ICMSTot></total>' if vnf else '')
        + f'{cobr}</infNFe></NFe>'
    )
    prot = (
        f'<protNFe><infProt><chNFe>{chave}</chNFe><cStat>{cstat}</cStat>'
        f'<xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe>'
    ) if protocolo else ""
    corpo = f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">{nfe}{prot}</nfeProc>' if protocolo \
        else nfe.replace("<NFe>", '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">')
    return ('<?xml version="1.0" encoding="UTF-8"?>' + corpo).encode("utf-8")


class ImportacaoXmlTests(BaseComercialTest):
    def importar(self, conteudo, nome="nota.xml"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(
            reverse("comercial:compras_importar"),
            {"arquivo": SimpleUploadedFile(nome, conteudo, content_type="text/xml")},
        )

    def mensagens(self, resp):
        return [str(m) for m in resp.wsgi_request._messages]

    def test_importa_nota_e_cria_fornecedor_pelo_cnpj(self):
        resp = self.importar(nfe_xml())
        compra = Compra.objects.get()
        self.assertRedirects(resp, reverse("comercial:vincular_itens", args=[compra.id]))
        self.assertEqual(compra.chave_acesso, "35261012345678000199550010000012341000012345")
        self.assertEqual(compra.fornecedor.documento, "12.345.678/0001-99")
        self.assertEqual(compra.fornecedor.tipo, "FORNECEDOR")
        self.assertEqual(compra.valor_total, Decimal("100.00"))
        item = compra.itens.get()
        self.assertEqual((item.codigo_fornecedor, item.ean, item.ncm, item.unidade_fornecedor),
                         ("A1", "7891234567895", "73181500", "CX"))
        self.assertEqual(item.status, "pendente")

    def test_usa_fornecedor_existente_com_cnpj_formatado(self):
        existente = Contato.objects.create(nome="Distribuidora", tipo="FORNECEDOR", documento="12.345.678/0001-99")
        self.importar(nfe_xml())
        self.assertEqual(Compra.objects.get().fornecedor, existente)

    def test_bloqueia_nota_repetida_pela_chave(self):
        self.importar(nfe_xml())
        resp = self.importar(nfe_xml(numero="9999"))
        self.assertEqual(Compra.objects.count(), 1)
        self.assertTrue(any("já foi importada" in m for m in self.mensagens(resp)))

    def test_recusa_xml_sem_protocolo(self):
        resp = self.importar(nfe_xml(protocolo=False))
        self.assertEqual(Compra.objects.count(), 0)
        self.assertTrue(any("protocolo" in m for m in self.mensagens(resp)))

    def test_recusa_nota_nao_autorizada(self):
        self.importar(nfe_xml(cstat="110"))
        self.assertEqual(Compra.objects.count(), 0)

    def test_recusa_nota_de_outro_destinatario(self):
        with self.settings(EMPRESA_CNPJ="11111111000111"):
            resp = self.importar(nfe_xml())
        self.assertEqual(Compra.objects.count(), 0)
        self.assertTrue(any("outro destinatário" in m for m in self.mensagens(resp)))

    def test_vincula_automatico_pelo_ean(self):
        self.produto.ean = "7891234567895"
        self.produto.save()
        self.importar(nfe_xml())
        item = CompraItem.objects.get()
        self.assertEqual((item.produto, item.status), (self.produto, "vinculado"))

    def test_lembra_vinculo_e_fator_na_proxima_nota(self):
        self.importar(nfe_xml())
        compra = Compra.objects.get()
        item = compra.itens.get()
        self.client.post(reverse("comercial:vincular_itens", args=[compra.id]), {
            f"produto_{item.id}": self.produto.id, f"fator_{item.id}": "50",
        })
        self.importar(nfe_xml(chave="35261012345678000199550010000012351000012346", numero="1235"))
        novo = Compra.objects.get(numero_nota="1235").itens.get()
        self.assertEqual(novo.produto, self.produto)
        self.assertEqual(novo.fator_conversao, Decimal("50"))
        self.assertEqual(novo.status, "vinculado")

    def test_fator_converte_quantidade_e_custo_no_estoque(self):
        self.importar(nfe_xml())
        compra = Compra.objects.get()
        item = compra.itens.get()
        self.client.post(reverse("comercial:vincular_itens", args=[compra.id]), {
            f"produto_{item.id}": self.produto.id, f"fator_{item.id}": "50",
        })
        self.client.post(reverse("comercial:compras_finalizar_avista", args=[compra.id]))
        estoque = self.estoque()
        self.assertEqual(estoque.quantidade, Decimal("100"))
        self.assertEqual(estoque.preco_medio, Decimal("1.00"))
        self.assertEqual(FinanceiroPagar.objects.get().valor, Decimal("100.00"))

    def test_fator_invalido_nao_salva(self):
        self.importar(nfe_xml())
        compra = Compra.objects.get()
        item = compra.itens.get()
        self.client.post(reverse("comercial:vincular_itens", args=[compra.id]), {
            f"produto_{item.id}": self.produto.id, f"fator_{item.id}": "0",
        })
        item.refresh_from_db()
        self.assertEqual(item.status, "pendente")

    def test_cria_produto_novo_a_partir_do_item(self):
        self.importar(nfe_xml(itens=[("B7", "SEM GTIN", "Cola branca 1kg", "KG", "3.5", "10.00")]))
        compra = Compra.objects.get()
        item = compra.itens.get()
        resp = self.client.post(reverse("comercial:vincular_itens", args=[compra.id]), {
            f"produto_{item.id}": "novo", f"fator_{item.id}": "1",
        })
        self.assertRedirects(resp, reverse("comercial:compras_confirmar", args=[compra.id]))
        item.refresh_from_db()
        self.assertEqual(item.status, "novo_produto")
        self.assertEqual((item.produto.codor, item.produto.descricao, item.produto.unidade, item.produto.ncm),
                         ("B7", "Cola branca 1kg", "KG", "73181500"))
        self.assertEqual(item.ean, "")

    def test_telas_de_vinculo_e_confirmacao_abrem(self):
        self.importar(nfe_xml())
        compra = Compra.objects.get()
        resp = self.client.get(reverse("comercial:vincular_itens", args=[compra.id]))
        self.assertContains(resp, "Distribuidora X")
        item = compra.itens.get()
        self.client.post(reverse("comercial:vincular_itens", args=[compra.id]), {
            f"produto_{item.id}": self.produto.id, f"fator_{item.id}": "50",
        })
        resp = self.client.get(reverse("comercial:compras_confirmar", args=[compra.id]))
        self.assertContains(resp, "100 UN")

    def test_compra_finalizada_nao_permite_revincular(self):
        self.importar(nfe_xml())
        compra = Compra.objects.get()
        compra.confirmada = True
        compra.save()
        resp = self.client.get(reverse("comercial:vincular_itens", args=[compra.id]))
        self.assertEqual(resp.status_code, 302)


IMPOSTO_ST = (
    "<imposto><ICMS><ICMS10><vICMS>12.00</vICMS><vICMSST>8.00</vICMSST><vFCPST>2.00</vFCPST></ICMS10></ICMS>"
    "<IPI><IPITrib><vIPI>5.00</vIPI></IPITrib></IPI>"
    "<PIS><PISAliq><vPIS>1.65</vPIS></PISAliq></PIS><COFINS><COFINSAliq><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS></imposto>"
)
PROD_DESPESAS = "<vFrete>10.00</vFrete><vSeg>1.00</vSeg><vDesc>6.00</vDesc><vOutro>4.00</vOutro>"
DUPLICATAS = (
    "<cobr><dup><nDup>001</nDup><dVenc>2026-11-10</dVenc><vDup>60.00</vDup></dup>"
    "<dup><nDup>002</nDup><dVenc>2026-12-10</dVenc><vDup>64.00</vDup></dup></cobr>"
)


class ImportacaoXmlCustoTests(BaseComercialTest):
    importar = ImportacaoXmlTests.importar
    mensagens = ImportacaoXmlTests.mensagens

    def importar_vinculado(self, **kwargs):
        self.importar(nfe_xml(**kwargs))
        compra = Compra.objects.get()
        item = compra.itens.get()
        self.client.post(reverse("comercial:vincular_itens", args=[compra.id]), {
            f"produto_{item.id}": self.produto.id, f"fator_{item.id}": "50",
        })
        return compra

    def test_total_da_compra_inclui_despesas_ipi_e_st(self):
        # 100 de produtos + 10 frete + 1 seguro + 4 outras - 6 desconto + 5 IPI + 10 ST/FCP-ST
        compra = self.importar_vinculado(prod_extra=PROD_DESPESAS, imposto=IMPOSTO_ST, vnf="124.00")
        self.assertEqual(compra.valor_total, Decimal("124.00"))
        item = compra.itens.get()
        self.assertEqual((item.valor_icms, item.valor_pis, item.valor_cofins),
                         (Decimal("12.00"), Decimal("1.65"), Decimal("7.60")))

    def test_custo_no_estoque_inclui_despesas(self):
        compra = self.importar_vinculado(prod_extra=PROD_DESPESAS, imposto=IMPOSTO_ST)
        self.client.post(reverse("comercial:compras_finalizar_avista", args=[compra.id]))
        estoque = self.estoque()
        self.assertEqual(estoque.quantidade, Decimal("100"))
        self.assertEqual(estoque.preco_medio, Decimal("1.24"))
        self.assertEqual(FinanceiroPagar.objects.get().valor, Decimal("124.00"))

    def test_creditos_abatem_do_custo(self):
        compra = self.importar_vinculado(prod_extra=PROD_DESPESAS, imposto=IMPOSTO_ST)
        with self.settings(COMPRA_CREDITOS={"ICMS", "PIS", "COFINS"}):
            self.client.post(reverse("comercial:compras_finalizar_avista", args=[compra.id]))
        # 124 - 12 - 1,65 - 7,60 = 102,75 por 100 UN
        self.assertEqual(self.estoque().preco_medio, Decimal("1.03"))
        self.assertEqual(FinanceiroPagar.objects.get().valor, Decimal("124.00"))

    def test_aviso_quando_total_da_nota_difere(self):
        resp = self.importar(nfe_xml(vnf="150.00"))
        self.assertTrue(any("diferente da soma" in m for m in self.mensagens(resp)))

    def test_finaliza_pelas_duplicatas_da_nota(self):
        compra = self.importar_vinculado(prod_extra=PROD_DESPESAS, imposto=IMPOSTO_ST, cobr=DUPLICATAS)
        self.assertTrue(compra.duplicatas_conferem)
        resp = self.client.get(reverse("comercial:compras_confirmar", args=[compra.id]))
        self.assertContains(resp, "Conforme as duplicatas da nota (2)")
        self.client.post(reverse("comercial:compras_confirmar", args=[compra.id]), {"forma_pagamento": "duplicatas"})
        titulos = list(FinanceiroPagar.objects.order_by("data_vencimento").values_list("data_vencimento", "valor"))
        self.assertEqual(titulos, [(date(2026, 11, 10), Decimal("60.00")), (date(2026, 12, 10), Decimal("64.00"))])
        compra.refresh_from_db()
        self.assertTrue(compra.confirmada)
        self.assertEqual(self.estoque().quantidade, Decimal("100"))

    def test_duplicatas_que_nao_conferem_nao_sao_usadas(self):
        compra = self.importar_vinculado(cobr=DUPLICATAS)  # total 100, duplicatas 124
        self.assertFalse(compra.duplicatas_conferem)
        self.client.post(reverse("comercial:compras_finalizar_duplicatas", args=[compra.id]))
        self.assertEqual(FinanceiroPagar.objects.count(), 0)
        compra.refresh_from_db()
        self.assertFalse(compra.confirmada)

    def test_compra_manual_continua_igual(self):
        compra = self.criar_compra(quantidade=10, preco="5.00")
        self.assertEqual(compra.valor_total, Decimal("50.00"))
        self.client.post(reverse("comercial:compras_finalizar_avista", args=[compra.id]))
        self.assertEqual(self.estoque().preco_medio, Decimal("5.00"))


IMPOSTO_FISCAL = (
    "<imposto><ICMS><ICMS10><orig>0</orig><CST>10</CST><vBC>100.00</vBC><pICMS>12.0000</pICMS>"
    "<vICMS>12.00</vICMS><vBCST>140.00</vBCST><vICMSST>8.00</vICMSST></ICMS10></ICMS>"
    "<IPI><IPITrib><CST>50</CST><pIPI>5.0000</pIPI><vIPI>5.00</vIPI></IPITrib></IPI>"
    "<PIS><PISAliq><CST>01</CST><vPIS>1.65</vPIS></PISAliq></PIS>"
    "<COFINS><COFINSAliq><CST>01</CST><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS></imposto>"
)


class ImportacaoXmlFiscalTests(BaseComercialTest):
    importar = ImportacaoXmlTests.importar

    def test_guarda_classificacao_fiscal_do_item(self):
        self.importar(nfe_xml(prod_extra="<CFOP>5405</CFOP><CEST>1200100</CEST>", imposto=IMPOSTO_FISCAL))
        item = CompraItem.objects.get()
        self.assertEqual(
            (item.cfop, item.cest, item.origem, item.cst_icms, item.cst_pis, item.cst_cofins),
            ("5405", "1200100", "0", "10", "01", "01"),
        )
        self.assertEqual((item.base_icms, item.aliquota_icms, item.base_icms_st, item.aliquota_ipi),
                         (Decimal("100.00"), Decimal("12"), Decimal("140.00"), Decimal("5")))

    def test_csosn_do_simples(self):
        imposto = "<imposto><ICMS><ICMSSN102><orig>2</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS></imposto>"
        self.importar(nfe_xml(imposto=imposto))
        item = CompraItem.objects.get()
        self.assertEqual((item.origem, item.cst_icms), ("2", "102"))

    def test_produto_novo_recebe_cest(self):
        self.importar(nfe_xml(prod_extra="<CEST>1200100</CEST>"))
        compra = Compra.objects.get()
        item = compra.itens.get()
        self.client.post(reverse("comercial:vincular_itens", args=[compra.id]), {f"produto_{item.id}": "novo"})
        item.refresh_from_db()
        self.assertEqual(item.produto.cest, "1200100")

    def test_baixar_xml_da_compra(self):
        self.importar(nfe_xml())
        compra = Compra.objects.get()
        resp = self.client.get(reverse("comercial:compra_xml", args=[compra.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(compra.chave_acesso, resp["Content-Disposition"])
        self.assertIn(b"<nfeProc", resp.content)
        detalhe = self.client.get(reverse("comercial:compra_detalhe", args=[compra.id]))
        self.assertContains(detalhe, "Baixar XML")

    def test_reprocessar_preenche_itens_antigos_sem_mudar_valores(self):
        from django.core.management import call_command
        self.importar(nfe_xml(prod_extra="<CFOP>5405</CFOP>", imposto=IMPOSTO_FISCAL))
        compra = Compra.objects.get()
        # Simula compra importada antes desta versão
        CompraItem.objects.update(cfop="", cst_icms="", valor_icms=0, aliquota_icms=0)
        total_antes = compra.valor_total
        call_command("reprocessar_fiscal_nfe", stdout=io.StringIO())
        item = CompraItem.objects.get()
        self.assertEqual((item.cfop, item.cst_icms, item.valor_icms), ("5405", "10", Decimal("12.00")))
        compra.refresh_from_db()
        self.assertEqual(compra.valor_total, total_antes)


class CorrecaoCompraNfeTests(BaseComercialTest):
    importar = ImportacaoXmlTests.importar

    def test_total_usa_valor_dos_produtos_da_nota(self):
        # 3 x 3,3333 = 9,9999, mas a nota informa vProd 10,00
        self.importar(nfe_xml(itens=[("A1", "", "Item", "UN", "3", "3.3333")], prod_extra="<vProd>10.00</vProd>"))
        self.assertEqual(Compra.objects.get().valor_total, Decimal("10.00"))

    def test_corrige_compra_importada_antes_da_etapa_b(self):
        from django.core.management import call_command
        self.importar(nfe_xml(prod_extra="<vProd>100.00</vProd>" + PROD_DESPESAS, imposto=IMPOSTO_ST))
        compra = Compra.objects.get()
        item = compra.itens.get()
        self.client.post(reverse("comercial:vincular_itens", args=[compra.id]), {
            f"produto_{item.id}": self.produto.id, f"fator_{item.id}": "50",
        })
        # Simula a importação antiga: sem despesas, impostos e desconto
        CompraItem.objects.update(valor_frete=0, valor_seguro=0, valor_outras=0, valor_desconto=0,
                                  valor_ipi=0, valor_icms_st=0)
        compra.atualizar_valor_total()
        self.client.post(reverse("comercial:compras_finalizar_parcelado", args=[compra.id]), {
            "parcelas": 2, "dias_entre_parcelas": 30, "data_inicial": "2026-11-01",
        })
        self.assertEqual(self.estoque().preco_medio, Decimal("1.00"))

        call_command("corrigir_compra_nfe", compra.id, stdout=io.StringIO())
        self.assertEqual(self.estoque().preco_medio, Decimal("1.00"))  # sem --aplicar nada muda

        call_command("corrigir_compra_nfe", compra.id, "--aplicar", stdout=io.StringIO())
        compra.refresh_from_db()
        self.assertEqual(compra.valor_total, Decimal("124.00"))
        self.assertEqual(self.estoque().preco_medio, Decimal("1.24"))
        self.assertEqual(self.estoque().quantidade, Decimal("100"))
        self.assertEqual(sorted(FinanceiroPagar.objects.values_list("valor", flat=True)),
                         [Decimal("62.00"), Decimal("62.00")])


class VendaDescontoTests(BaseComercialTest):
    def test_desconto_e_acrescimo_da_venda_entram_no_total_e_no_receber(self):
        self.dar_entrada()
        venda = self.criar_venda()  # 2 × 20
        self.post_editar_venda(venda, 2, desconto="5.00", acrescimo="1.50")
        venda.refresh_from_db()
        self.assertEqual(venda.status, "finalizada")
        self.assertEqual(venda.total, Decimal("36.50"))
        titulo = FinanceiroReceber.objects.get(origem="VENDA", object_id=venda.id)
        self.assertEqual(titulo.valor, Decimal("36.50"))

    def test_desconto_maior_que_os_itens_e_recusado(self):
        self.dar_entrada()
        venda = self.criar_venda()
        resp = self.post_editar_venda(venda, 2, desconto="50.00")
        self.assertContains(resp, "maior que o total dos itens")
        venda.refresh_from_db()
        self.assertEqual(venda.status, "rascunho")
        self.assertEqual(venda.desconto, Decimal("0"))
        self.assertFalse(FinanceiroReceber.objects.filter(origem="VENDA", object_id=venda.id).exists())


class CorrigirCMVTests(BaseComercialTest):
    def test_cria_cmv_que_falta_a_partir_da_saida(self):
        from django.core.management import call_command
        from comercial.models import CMVItem
        self.dar_entrada(preco="4.00")
        venda = self.criar_venda()
        venda.status = "finalizada"
        venda.save()
        MovimentacaoEstoque.objects.create(produto=self.produto, tipo="SAIDA", quantidade=2,
                                           origem="VENDA", referencia_id=venda.id)
        call_command("corrigir_cmv", stdout=io.StringIO())
        self.assertFalse(CMVItem.objects.exists())  # sem --aplicar não grava
        call_command("corrigir_cmv", aplicar=True, stdout=io.StringIO())
        cmv = CMVItem.objects.get()
        self.assertEqual(cmv.total_cmv, Decimal("8.00"))
        venda.refresh_from_db()
        self.assertEqual(venda.cmv, Decimal("8.00"))


class LeitorCodigoBarrasTests(BaseComercialTest):
    # Leitor de código de barras da tela de venda
    def ler(self, codigo):
        return self.client.get(reverse("comercial:api_produto_codigo"), {"codigo": codigo})

    def test_encontra_pelo_ean(self):
        self.produto.ean = "7891234567895"
        self.produto.save()
        self.dar_entrada(3)
        self.produto.refresh_from_db()
        dados = self.ler(" 7891234567895 ").json()
        self.assertEqual(dados["id"], self.produto.id)
        self.assertEqual(dados["preco"], float(self.produto.preco_venda))
        self.assertEqual(dados["estoque"], 3)

    def test_encontra_pelo_ean_da_nota_do_fornecedor(self):
        from comercial.models import ProdutoFornecedor
        ProdutoFornecedor.objects.create(fornecedor=self.fornecedor, codigo_fornecedor="A1",
                                         ean="7890000000017", produto=self.produto)
        self.assertEqual(self.ler("7890000000017").json()["id"], self.produto.id)

    def test_ean_da_caixa_nao_vale_como_unidade(self):
        from comercial.models import ProdutoFornecedor
        ProdutoFornecedor.objects.create(fornecedor=self.fornecedor, codigo_fornecedor="CX",
                                         ean="7890000000024", produto=self.produto, fator_conversao=12)
        self.assertEqual(self.ler("7890000000024").status_code, 404)

    def test_sem_ean_usa_o_codigo_interno(self):
        self.assertEqual(self.ler("p1").json()["id"], self.produto.id)

    def test_codigo_desconhecido(self):
        resposta = self.ler("999")
        self.assertEqual(resposta.status_code, 404)
        self.assertIn("999", resposta.json()["erro"])

    def test_codigo_em_dois_produtos(self):
        Produto.objects.create(codor="P1", descricao="Outro com o mesmo código", unidade="UN")
        self.assertEqual(self.ler("P1").status_code, 409)

    def test_tela_de_venda_tem_leitor_e_cliente_rapido(self):
        html = self.client.get(reverse("comercial:venda_create")).content.decode()
        self.assertIn('id="leitor-codigo"', html)
        self.assertIn('id="modalNovoCliente"', html)
        self.assertIn(reverse("comercial:api_produto_codigo"), html)


class EscolherItemVendaTests(BaseComercialTest):
    # Modal "Escolher item" da tela de venda
    def listar(self):
        return self.client.get(reverse("comercial:api_itens_venda")).json()

    def test_so_lista_produtos_com_estoque(self):
        self.dar_entrada(4)
        Produto.objects.create(codor="P2", descricao="Sem estoque", unidade="UN")
        zerado = Produto.objects.create(codor="P3", descricao="Estoque zerado", unidade="UN")
        Estoque.objects.create(produto=zerado, quantidade=0)
        produtos = self.listar()["produtos"]
        self.assertEqual([p["id"] for p in produtos], [self.produto.id])
        self.assertEqual(produtos[0]["estoque"], 4)
        self.assertEqual(produtos[0]["codigo"], "P1")

    def test_lista_servicos_com_categoria(self):
        from cadastros.models import CategoriaServico, Servico
        iluminacao = CategoriaServico.objects.create(nome="Iluminação", ordem=1)
        CategoriaServico.objects.create(nome="Vazia", ordem=2)
        Servico.objects.create(codsv="SV001", descricao="Instalar luminária", unidade="UN",
                               preco_servico=Decimal("80.00"), categoria=iluminacao)
        Servico.objects.create(codsv="SV002", descricao="Visita técnica", unidade="UN")
        dados = self.listar()
        self.assertEqual([c["nome"] for c in dados["categorias"]], ["Iluminação"])
        self.assertEqual([(s["codigo"], s["categoria"], s["preco"]) for s in dados["servicos"]],
                         [("SV001", iluminacao.id, 80.0), ("SV002", None, 0.0)])

    def test_tela_de_venda_tem_coluna_item_e_modal(self):
        html = self.client.get(reverse("comercial:venda_create")).content.decode()
        self.assertIn('id="modalEscolherItem"', html)
        self.assertIn(reverse("comercial:api_itens_venda"), html)
        self.assertIn('class="btn btn-outline-secondary w-100 text-start item-escolher"', html)
        self.assertNotIn("select2-produto", html)

    def test_editar_venda_mostra_o_item_gravado(self):
        self.dar_entrada(5)
        venda = self.criar_venda(quantidade=2)
        html = self.client.get(reverse("comercial:venda_editar", args=[venda.id])).content.decode()
        self.assertIn(f'<option value="{self.produto.id}" selected>P1 - Produto 1</option>', html)
