# core/grupos.py
#
# Grupos (perfis) padrão do sistema e as permissões de cada um.
# Usado pela migração core 0001 e pelo comando "python manage.py criar_grupos".
# Depois de criados, os grupos podem ser ajustados livremente no admin (/admin/auth/group/).
#
# Cada item é "app.codigo" e aceita * (ex.: "financeiro.*" = tudo do financeiro).
# Item começando com "-" retira permissões (ex.: "-financeiro.delete_*").
from fnmatch import fnmatch

GRUPOS_PADRAO = {
    "Administrador": [
        "cadastros.*", "comercial.*", "financeiro.*", "relatorios.*",
        "auth.*_user", "auth.*_group",
    ],
    "Gerente": [
        "cadastros.*", "comercial.*", "financeiro.*", "relatorios.*",
        "-financeiro.delete_*",
        # No Painel o Gerente vê só Vendas e Estoque (as telas do Financeiro continuam liberadas)
        "-relatorios.painel_financeiro", "-relatorios.painel_clientes",
    ],
    "Vendedor": [
        "cadastros.view_contato", "cadastros.add_contato", "cadastros.change_contato",
        "cadastros.view_produto", "cadastros.view_servico",
        "comercial.view_venda", "comercial.add_venda", "comercial.change_venda",
        "comercial.*_vendaitem", "comercial.emitir_recibo",
        "comercial.view_estoque",
        "comercial.view_posvenda", "comercial.add_posvenda", "comercial.change_posvenda",
    ],
    "Compras/Estoque": [
        "cadastros.view_*", "cadastros.add_produto", "cadastros.change_produto",
        "cadastros.add_contato", "cadastros.change_contato", "cadastros.importar_csv",
        "comercial.*_compra", "comercial.*_compraitem", "comercial.*_compraduplicata",
        "comercial.*_produtofornecedor", "comercial.*_estoque", "comercial.*_movimentacaoestoque",
        "comercial.importar_nfe", "comercial.ver_custos",
        "relatorios.ver_comercial", "relatorios.painel_estoque",
    ],
    "Financeiro": [
        "cadastros.view_contato", "cadastros.view_produto", "cadastros.view_servico",
        "comercial.view_venda", "comercial.view_compra",
        "financeiro.*", "relatorios.*",
        "-relatorios.painel_vendas", "-relatorios.painel_estoque", "-relatorios.painel_clientes",
    ],
}


def permissoes_do_grupo(Permission, regras):
    # Devolve as permissões que casam com as regras do grupo
    todas = Permission.objects.select_related("content_type")
    escolhidas = []
    for perm in todas:
        nome = f"{perm.content_type.app_label}.{perm.codename}"
        incluir = any(fnmatch(nome, r) for r in regras if not r.startswith("-"))
        excluir = any(fnmatch(nome, r[1:]) for r in regras if r.startswith("-"))
        if incluir and not excluir:
            escolhidas.append(perm)
    return escolhidas


def criar_grupos(Group, Permission, redefinir=False):
    # Cria os grupos que não existem. Com redefinir=True, também volta os existentes ao padrão.
    resultado = []
    for nome, regras in GRUPOS_PADRAO.items():
        grupo, criado = Group.objects.get_or_create(name=nome)
        if criado or redefinir:
            grupo.permissions.set(permissoes_do_grupo(Permission, regras))
        resultado.append((nome, criado))
    return resultado
