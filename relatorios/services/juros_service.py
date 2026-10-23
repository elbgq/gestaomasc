from decimal import Decimal

from financeiro.models import FinanceiroLancamento, FinanceiroPagar, FinanceiroReceber

ZERO = Decimal("0.00")
COLUNAS = ("valor", "juros", "multa", "desconto", "total")
GRUPO_FINANCEIRO = {"D": "DESPESAS_FINANCEIRAS", "R": "RECEITAS_FINANCEIRAS"}


def _somar(linhas):
    totais = {c: sum((l[c] for l in linhas), ZERO) for c in COLUNAS}
    totais["juros_multa"] = totais["juros"] + totais["multa"]
    return totais


# Títulos quitados no período com juros, multa ou desconto, pela data da quitação
# (o mesmo critério do DRE, em acrescimos_das_quitacoes)
def quitacoes_com_encargos(modelo, data_inicio, data_fim):
    contato = "contato" if modelo is FinanceiroPagar else "cliente"
    titulos = modelo.objects.filter(
        status="pago", data_pagamento__gte=data_inicio, data_pagamento__lte=data_fim
    ).exclude(
        valor_juros=0, valor_multa=0, valor_desconto=0
    ).select_related(contato, "categoria", "caixa_movimento").order_by("data_pagamento", "id")

    return [{
        "data": t.data_pagamento,
        "titulo": t,
        "descricao": t.descricao,
        "origem": t.get_origem_display(),
        "contato": getattr(t, contato),
        "vencimento": t.data_vencimento,
        "atraso": max((t.data_pagamento - t.data_vencimento).days, 0),
        "caixa_movimento": t.caixa_movimento,
        "lancado": False,
        "valor": t.valor_pago or ZERO,
        "juros": t.valor_juros,
        "multa": t.valor_multa,
        "desconto": t.valor_desconto,
        "total": t.total_quitado(),
    } for t in titulos]


# Lançamentos e contas manuais em categorias de Despesas (tipo "D") ou Receitas (tipo "R") Financeiras,
# pela competência (o mesmo critério do DRE, em valores_por_grupo_dre). Ex.: juros lançados à mão.
# O valor vai na coluna Multa quando a categoria fala em multa; senão, na coluna Juros.
def financeiros_lancados(tipo, data_inicio, data_fim):
    grupo = GRUPO_FINANCEIRO[tipo]
    itens = []
    for lanc in FinanceiroLancamento.objects.filter(
        data__gte=data_inicio, data__lte=data_fim, categoria__grupo_dre=grupo
    ).select_related("categoria", "contato"):
        itens.append((lanc.data, lanc.descricao, "Lançamento", lanc.contato, lanc.categoria, lanc.valor, lanc.get_titulo()))

    if tipo == "D":
        titulos = FinanceiroPagar.objects.filter(origem="MANUAL").select_related("contato")
    else:
        titulos = FinanceiroReceber.objects.filter(origem__in=["MANUAL", "RECEITA"]).select_related("cliente")
    for t in titulos.filter(
        data_lancamento__gte=data_inicio, data_lancamento__lte=data_fim, categoria__grupo_dre=grupo
    ).exclude(status="cancelado").select_related("categoria"):
        contato = t.contato if tipo == "D" else t.cliente
        itens.append((t.data_lancamento, t.descricao, "Manual", contato, t.categoria, t.valor, t))

    linhas = []
    for data, descricao, origem, contato, categoria, valor, titulo in sorted(itens, key=lambda i: i[0]):
        multa = "multa" in categoria.nome.lower()
        linhas.append({
            "data": data,
            "titulo": titulo,
            "descricao": descricao,
            "origem": origem,
            "categoria": categoria,
            "contato": contato,
            "vencimento": titulo.data_vencimento if titulo else None,
            "atraso": None,
            "caixa_movimento": titulo.caixa_movimento if titulo else None,
            "lancado": True,
            "valor": ZERO,
            "juros": ZERO if multa else valor,
            "multa": valor if multa else ZERO,
            "desconto": ZERO,
            "total": valor,
        })
    return linhas


# Cada bloco (contas pagas, contas recebidas) traz as quitações com encargos e, depois, os lançados à mão.
# Os subtotais separados batem com as linhas do DRE: quitações = juros/multas e descontos;
# lançados = receitas ou despesas financeiras lançadas.
def _bloco(modelo, tipo, data_inicio, data_fim):
    quitacoes = quitacoes_com_encargos(modelo, data_inicio, data_fim)
    lancados = financeiros_lancados(tipo, data_inicio, data_fim)
    return {
        "linhas": quitacoes + lancados,
        "totais": _somar(quitacoes),
        "totais_lancados": _somar(lancados),
        "totais_geral": _somar(quitacoes + lancados),
        "tem_lancados": bool(lancados),
    }


def juros_multas_descontos(data_inicio, data_fim):
    return {
        "pagar": _bloco(FinanceiroPagar, "D", data_inicio, data_fim),
        "receber": _bloco(FinanceiroReceber, "R", data_inicio, data_fim),
    }
