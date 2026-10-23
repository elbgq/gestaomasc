from decimal import Decimal

from financeiro.models import FinanceiroLancamento, FinanceiroPagar, FinanceiroReceber

ZERO = Decimal("0.00")
GRUPOS_FINANCEIROS = ("RECEITAS_FINANCEIRAS", "DESPESAS_FINANCEIRAS")


# Títulos quitados no período com juros, multa ou desconto, pela data da quitação
# (o mesmo critério do DRE, em acrescimos_das_quitacoes). Devolve as linhas e os totais por coluna.
def quitacoes_com_encargos(modelo, data_inicio, data_fim):
    contato = "contato" if modelo is FinanceiroPagar else "cliente"
    titulos = modelo.objects.filter(
        status="pago", data_pagamento__gte=data_inicio, data_pagamento__lte=data_fim
    ).exclude(
        valor_juros=0, valor_multa=0, valor_desconto=0
    ).select_related(contato, "categoria", "caixa_movimento").order_by("data_pagamento", "id")

    linhas = []
    totais = {"valor": ZERO, "juros": ZERO, "multa": ZERO, "desconto": ZERO, "total": ZERO}
    for t in titulos:
        linha = {
            "titulo": t,
            "contato": getattr(t, contato),
            "atraso": max((t.data_pagamento - t.data_vencimento).days, 0),
            "valor": t.valor_pago or ZERO,
            "juros": t.valor_juros,
            "multa": t.valor_multa,
            "desconto": t.valor_desconto,
            "total": t.total_quitado(),
        }
        for campo in totais:
            totais[campo] += linha[campo]
        linhas.append(linha)
    totais["juros_multa"] = totais["juros"] + totais["multa"]
    return {"linhas": linhas, "totais": totais}


# Lançamentos e títulos manuais em categorias de Receitas ou Despesas Financeiras, pela competência
# (o mesmo critério do DRE, em valores_por_grupo_dre). Ex.: juros lançados à mão como despesa.
def financeiros_lancados(data_inicio, data_fim):
    linhas = []
    for lanc in FinanceiroLancamento.objects.filter(
        data__gte=data_inicio, data__lte=data_fim, categoria__grupo_dre__in=GRUPOS_FINANCEIROS
    ).select_related("categoria", "contato"):
        linhas.append({"data": lanc.data, "origem": "Lançamento", "lancamento": lanc, "titulo": lanc.get_titulo(),
                       "contato": lanc.contato, "descricao": lanc.descricao, "categoria": lanc.categoria,
                       "valor": lanc.valor})

    for modelo, origens, contato in ((FinanceiroPagar, ["MANUAL"], "contato"),
                                     (FinanceiroReceber, ["MANUAL", "RECEITA"], "cliente")):
        for t in modelo.objects.filter(
            origem__in=origens, data_lancamento__gte=data_inicio, data_lancamento__lte=data_fim,
            categoria__grupo_dre__in=GRUPOS_FINANCEIROS,
        ).exclude(status="cancelado").select_related("categoria", contato):
            linhas.append({"data": t.data_lancamento, "origem": "Conta manual", "lancamento": None, "titulo": t,
                           "contato": getattr(t, contato), "descricao": t.descricao, "categoria": t.categoria,
                           "valor": t.valor})

    linhas.sort(key=lambda l: l["data"])
    receitas = sum((l["valor"] for l in linhas if l["categoria"].grupo_dre == "RECEITAS_FINANCEIRAS"), ZERO)
    despesas = sum((l["valor"] for l in linhas if l["categoria"].grupo_dre == "DESPESAS_FINANCEIRAS"), ZERO)
    return {"linhas": linhas, "totais": {"receitas": receitas, "despesas": despesas}}


def juros_multas_descontos(data_inicio, data_fim):
    return {
        "pagar": quitacoes_com_encargos(FinanceiroPagar, data_inicio, data_fim),
        "receber": quitacoes_com_encargos(FinanceiroReceber, data_inicio, data_fim),
        "lancados": financeiros_lancados(data_inicio, data_fim),
    }
