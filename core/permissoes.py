# core/permissoes.py
#
# Mapa único de permissões: nome da rota -> permissão exigida para abrir a tela.
# O PermissaoMiddleware (core/middleware.py), o menu e os botões consultam este mapa.
#
#   texto  -> o usuário precisa dessa permissão
#   tupla  -> basta ter uma das permissões
#   função -> recebe os parâmetros da URL e devolve a permissão (texto ou tupla)
#
# Rota dos módulos abaixo que não estiver no mapa fica BLOQUEADA para quem não é superusuário.
# Ao criar uma tela nova, acrescente a rota aqui (o teste core.tests avisa se faltar).

MODULOS_PROTEGIDOS = ("cadastros", "comercial", "financeiro", "relatorios")


def _titulo(acao):
    # Títulos usam a mesma URL para pagar (D) e receber (R)
    def regra(kwargs):
        modelo = {"D": "financeiropagar", "R": "financeiroreceber"}.get(kwargs.get("tipo"))
        return f"financeiro.{acao}_{modelo}" if modelo else None
    return regra


PERMISSOES = {
    # ---------------- Cadastros ----------------
    "cadastros:produto_list": "cadastros.view_produto",
    "cadastros:produto_detail": "cadastros.view_produto",
    "cadastros:produto_create": "cadastros.add_produto",
    "cadastros:produto_create_ajax": "cadastros.add_produto",
    "cadastros:produto_update": "cadastros.change_produto",
    "cadastros:produto_delete": "cadastros.delete_produto",
    "cadastros:importar_produtos": "cadastros.importar_csv",
    "cadastros:revisao_precos": "cadastros.revisar_precos",

    "cadastros:servico_list": "cadastros.view_servico",
    "cadastros:servico_detail": "cadastros.view_servico",
    "cadastros:servico_create": "cadastros.add_servico",
    "cadastros:servico_update": "cadastros.change_servico",
    "cadastros:servico_delete": "cadastros.delete_servico",
    "cadastros:importar_servicos": "cadastros.importar_csv",

    "cadastros:contato_list": "cadastros.view_contato",
    "cadastros:contato_detail": "cadastros.view_contato",
    "cadastros:contato_create": "cadastros.add_contato",
    "cadastros:contato_update": "cadastros.change_contato",
    "cadastros:contato_delete": "cadastros.delete_contato",
    "cadastros:contato_unificar": "cadastros.unificar_contato",

    # ---------------- Comercial: compras ----------------
    "comercial:compra_list": "comercial.view_compra",
    "comercial:compra_detalhe": "comercial.view_compra",
    "comercial:compra_xml": "comercial.view_compra",
    "comercial:compra_criar": "comercial.add_compra",
    "comercial:compra_editar": "comercial.change_compra",
    "comercial:compra_excluir": "comercial.delete_compra",
    "comercial:compras_finalizar_avista": ("comercial.add_compra", "comercial.change_compra"),
    "comercial:compras_finalizar_parcelado": ("comercial.add_compra", "comercial.change_compra"),
    "comercial:compras_finalizar_duplicatas": ("comercial.add_compra", "comercial.change_compra"),
    "comercial:compras_importar": "comercial.importar_nfe",
    "comercial:vincular_itens": "comercial.importar_nfe",
    "comercial:compras_confirmar": ("comercial.add_compra", "comercial.change_compra"),

    # ---------------- Comercial: estoque e CMV ----------------
    "comercial:estoque_list": "comercial.view_estoque",
    "comercial:movimentacao_list": "comercial.view_movimentacaoestoque",
    "comercial:estoque_relatorio": "comercial.view_movimentacaoestoque",
    # Consultado pelas telas de venda e compra
    "comercial:ajax_estoque": ("comercial.view_estoque", "comercial.add_venda", "comercial.change_venda",
                               "comercial.add_compra", "comercial.change_compra"),
    "comercial:cmv_lista": "comercial.ver_custos",
    "comercial:cmv_detalhe": "comercial.ver_custos",

    # ---------------- Comercial: vendas ----------------
    "comercial:venda_list": "comercial.view_venda",
    "comercial:venda_detalhe": "comercial.view_venda",
    "comercial:venda_create": "comercial.add_venda",
    "comercial:venda_editar": "comercial.change_venda",
    "comercial:venda_parcelamento": ("comercial.add_venda", "comercial.change_venda"),
    "comercial:venda_excluir": "comercial.delete_venda",
    "comercial:venda_recibo": "comercial.emitir_recibo",
    "comercial:api_preco": ("comercial.add_venda", "comercial.change_venda"),

    # ---------------- Financeiro ----------------
    "financeiro:categoria_list": "financeiro.view_financeirocategoria",
    "financeiro:categoria_create": "financeiro.add_financeirocategoria",
    "financeiro:categoria_update": "financeiro.change_financeirocategoria",
    "financeiro:categoria_delete": "financeiro.delete_financeirocategoria",

    "financeiro:lancamento_list": "financeiro.view_financeirolancamento",
    "financeiro:lancamento_create": "financeiro.add_financeirolancamento",
    "financeiro:lancamento_update": "financeiro.change_financeirolancamento",
    "financeiro:lancamento_delete": "financeiro.delete_financeirolancamento",

    "financeiro:receber_list": "financeiro.view_financeiroreceber",
    "financeiro:receber_create": "financeiro.add_financeiroreceber",
    "financeiro:receber_update": "financeiro.change_financeiroreceber",
    "financeiro:receber_delete": "financeiro.delete_financeiroreceber",

    "financeiro:contas_pagar_lista": "financeiro.view_financeiropagar",
    "financeiro:conta_detalhe": "financeiro.view_financeiropagar",
    "financeiro:pagar_update": "financeiro.change_financeiropagar",
    "financeiro:pagar_delete": "financeiro.delete_financeiropagar",
    "financeiro:pagar_titulo": "financeiro.quitar_titulo",

    "financeiro:titulo_list": ("financeiro.view_financeiropagar", "financeiro.view_financeiroreceber"),
    "financeiro:titulo_detalhe": _titulo("view"),
    "financeiro:titulo_confirmar_quitacao": "financeiro.quitar_titulo",
    "financeiro:titulo_estornar_quitacao": "financeiro.estornar_quitacao",
    "financeiro:titulo_reclassificar": "financeiro.reclassificar_titulo",
    # Sugestão de categoria usada nos formulários de lançamento e contas
    "financeiro:api_categoria_sugerida": ("financeiro.add_financeirolancamento", "financeiro.change_financeirolancamento",
                                          "financeiro.add_financeiroreceber", "financeiro.change_financeiroreceber",
                                          "financeiro.add_financeiropagar", "financeiro.change_financeiropagar"),

    "financeiro:caixa_list": "financeiro.view_caixamovimento",
    "financeiro:caixa_detalhe": "financeiro.view_caixamovimento",
    "financeiro:caixa_historico": "financeiro.view_caixamovimento",
    "financeiro:caixa_movimento_detalhe": "financeiro.view_caixamovimento",
    "financeiro:caixa_create": "financeiro.add_caixamovimento",
    "financeiro:caixa_update": "financeiro.change_caixamovimento",
    "financeiro:caixa_delete": "financeiro.delete_caixamovimento",
    "financeiro:caixa_abrir": "financeiro.operar_caixa",
    "financeiro:caixa_fechar": "financeiro.operar_caixa",
    "financeiro:caixa_sangria": "financeiro.operar_caixa",
    "financeiro:caixa_reforco": "financeiro.operar_caixa",

    "financeiro:dashboard": ("financeiro.view_financeiropagar", "financeiro.view_financeiroreceber"),

    # ---------------- Relatórios ----------------
    "relatorios:compras_por_periodo": "relatorios.ver_comercial",
    "relatorios:vendas_por_periodo": "relatorios.ver_comercial",
    "relatorios:movimentacoes_estoque": "relatorios.ver_comercial",
    "relatorios:cmv_relatorio": "relatorios.ver_gerencial",
    "relatorios:dre": "relatorios.ver_gerencial",
    "relatorios:juros_multas": "relatorios.ver_gerencial",
}


def pode_acessar(user, rota, kwargs=None):
    # Diz se o usuário pode abrir a rota (ex.: "financeiro:titulo_detalhe")
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if rota.split(":")[0] not in MODULOS_PROTEGIDOS:
        return True  # início, login, logout; o admin tem controle próprio

    regra = PERMISSOES.get(rota)
    if callable(regra):
        regra = regra(kwargs or {})
    if not regra:
        return False
    if isinstance(regra, str):
        return user.has_perm(regra)
    return any(user.has_perm(p) for p in regra)
