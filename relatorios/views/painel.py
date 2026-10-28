from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format

from core.permissoes import pode_acessar

from relatorios.services import painel as srv

# Permissão de cada bloco do Painel (o mapa em core/permissoes.py abre a tela para quem tem qualquer uma)
BLOCOS = {
    "financeiro": "relatorios.painel_financeiro",
    "vendas": "relatorios.painel_vendas",
    "estoque": "relatorios.painel_estoque",
    "clientes": "relatorios.painel_clientes",
}


def painel(request):
    user = request.user
    hoje = timezone.localdate()
    per = srv.periodo(request.GET.get("periodo", "mes"), hoje)
    atualizar = "atualizar" in request.GET
    ver_custos = user.has_perm("comercial.ver_custos")
    ver = {nome: user.has_perm(perm) for nome, perm in BLOCOS.items()}

    # Cada bloco fica 5 minutos no cache, separado por período e por quem vê custo
    sufixo = f"{hoje}:{per['codigo']}:{int(ver_custos)}"
    contexto = {"per": per, "periodos": srv.PERIODOS, "ver": ver, "ver_custos": ver_custos}
    if ver["vendas"]:
        contexto["vendas"] = srv.em_cache(f"painel:vendas:{sufixo}", lambda: srv.bloco_vendas(per, ver_custos), atualizar)
        contexto["meta"] = srv.em_cache(f"painel:meta:{hoje}:{per['codigo']}", lambda: srv.bloco_meta(per, hoje), atualizar)
    if ver["estoque"]:
        contexto["estoque"] = srv.em_cache(f"painel:estoque:{sufixo}", lambda: srv.bloco_estoque(per, hoje, ver_custos), atualizar)
    if ver["clientes"]:
        contexto["clientes"] = srv.em_cache(f"painel:clientes:{hoje}:{per['codigo']}", lambda: srv.bloco_clientes(per, hoje), atualizar)
    if ver["financeiro"]:
        contexto["financeiro"] = srv.em_cache(f"painel:financeiro:{hoje}", lambda: srv.bloco_financeiro(hoje), atualizar)
        # Resultado do período: as contas da DRE, para quem pode ver a DRE
        if user.has_perm("relatorios.ver_gerencial"):
            contexto["resultado"] = srv.em_cache(f"painel:resultado:{hoje}:{per['codigo']}",
                                                 lambda: srv.bloco_resultado(per), atualizar)
    contexto["calculado_em"] = timezone.localtime()
    contexto["alertas"] = alertas(contexto)
    contexto["links"] = links(user)
    textos(contexto)
    return render(request, "relatorios/painel.html", contexto)


def alertas(ctx):
    # O que pede ação hoje, só dos blocos que o usuário vê: (texto, rota, cor)
    lista = []
    fin, est, ven = ctx.get("financeiro"), ctx.get("estoque"), ctx.get("vendas")
    if fin and fin["receber_vencido_n"]:
        lista.append((f"{fin['receber_vencido_n']} título(s) a receber vencido(s)", "financeiro:receber_list", "danger"))
    if fin and fin["pagar_vencido_n"]:
        lista.append((f"{fin['pagar_vencido_n']} conta(s) a pagar vencida(s)", "financeiro:contas_pagar_lista", "danger"))
    if fin and fin["fluxo"]["negativo_em"]:
        lista.append((f"Saldo previsto fica negativo em {fin['fluxo']['negativo_em']:%d/%m}", "financeiro:contas_pagar_lista", "danger"))
    if est and est["abaixo_qtd"]:
        lista.append((f"{est['abaixo_qtd']} produto(s) abaixo do estoque mínimo", "comercial:estoque_list", "warning"))
    if est and est["compras_pendentes"]:
        lista.append((f"{est['compras_pendentes']} compra(s) sem confirmar", "comercial:compra_list", "warning"))
    cli = ctx.get("clientes")
    if cli and cli["pos_venda"]["atrasados"]:
        lista.append((f"{cli['pos_venda']['atrasados']} pós-venda(s) com retorno atrasado", "comercial:posvenda_list", "danger"))
    if ven and ven["rascunhos"]:
        lista.append((f"{ven['rascunhos']} venda(s) em rascunho", "comercial:venda_list", "info"))
    return lista


# Telas que o Painel abre ao clicar; vazio quando o usuário não pode abrir
LINKS = {
    "caixa": "financeiro:caixa_historico",
    "receber": "financeiro:receber_list",
    "pagar": "financeiro:contas_pagar_lista",
    "vendas": "comercial:venda_list",
    "rel_vendas": "relatorios:vendas_por_periodo",
    "estoque": "comercial:estoque_list",
    "compras": "comercial:compra_list",
    "precos": "cadastros:revisao_precos",
    "dre": "relatorios:dre",
    "clientes": "cadastros:contato_list",
    "posvenda": "comercial:posvenda_list",
    "posvenda_novo": "comercial:posvenda_criar",
    "metas": "comercial:meta_list",
    "meta_nova": "comercial:meta_criar",
}


def links(user):
    return {nome: reverse(rota) if pode_acessar(user, rota) else "" for nome, rota in LINKS.items()}


def reais(valor):
    return number_format(valor, 2, force_grouping=True)


def textos(ctx):
    # Linhas menores dos cartões que juntam número e texto
    ven, est, res, cli = ctx.get("vendas"), ctx.get("estoque"), ctx.get("resultado"), ctx.get("clientes")
    if cli:
        cli["recompra_txt"] = (f"{number_format(cli['recompra_pct'], 1)}% dos clientes do período já compraram mais de uma vez"
                               if cli["recompra_pct"] is not None else "sem clientes no período")
        cli["inad_txt"] = (f"{number_format(cli['inad_pct'], 1)}% dos R$ {reais(cli['inad_aberto'])} em aberto"
                           if cli["inad_pct"] is not None else "nada em aberto")
        cli["atraso_txt"] = (f"{number_format(cli['em_dia_pct'], 1)}% pagos em dia ({cli['recebidos_qtd']} título(s))"
                             if cli["atraso_medio"] is not None else "nenhum título recebido no período")
    if res:
        res["margem_txt"] = (f"{number_format(res['margem_liquida'], 1)}% da receita líquida"
                             if res["margem_liquida"] is not None else "sem receita no período")
    if ven:
        ven["ticket_txt"] = reais(ven["ticket"])
        if "margem" in ven:
            ven["margem_txt"] = (f"{number_format(ven['margem_pct'], 1)}% do faturamento" if ven["margem_pct"] is not None
                                 else "sem vendas no período")
    if est and "valor" in est:
        dias = est["cobertura_dias"]
        if dias is None:
            est["cobertura_txt"] = "sem saídas nos últimos 90 dias"
        elif dias > 365:
            est["cobertura_txt"] = "dura mais de 1 ano no ritmo atual"
        else:
            est["cobertura_txt"] = f"dura cerca de {dias} dias no ritmo atual"
