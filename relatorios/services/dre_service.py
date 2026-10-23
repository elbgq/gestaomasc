from decimal import Decimal
from django.db.models import Sum
from comercial.models import VendaItem, CMVItem, Venda
from financeiro.models import FinanceiroCategoria, FinanceiroLancamento, FinanceiroPagar, FinanceiroReceber

GRUPOS_DRE = {codigo for codigo, _ in FinanceiroCategoria.GRUPO_DRE_CHOICES}


# Soma por grupo do DRE, pela data de competência (data do lançamento), de:
# - lançamentos financeiros;
# - contas a pagar e a receber criadas direto (manuais), que não têm lançamento.
# Títulos de venda, de compra e de lançamento ficam de fora: a venda entra pela receita e
# pelo CMV, a compra vira estoque e o lançamento já foi contado. A data de pagamento não importa.
# Devolve também o que ficou fora do DRE (categoria sem grupo), para a tela avisar.
def valores_por_grupo_dre(data_inicio, data_fim):
    valores = []
    for lanc in FinanceiroLancamento.objects.filter(
        data__gte=data_inicio, data__lte=data_fim
    ).select_related("categoria"):
        valores.append((lanc.categoria, lanc.valor))

    for modelo, origens in ((FinanceiroPagar, ["MANUAL"]), (FinanceiroReceber, ["MANUAL", "RECEITA"])):
        for titulo in modelo.objects.filter(
            origem__in=origens, data_lancamento__gte=data_inicio, data_lancamento__lte=data_fim
        ).exclude(status="cancelado").select_related("categoria"):
            valores.append((titulo.categoria, titulo.valor))

    grupos, fora = {}, {}
    for categoria, valor in valores:
        grupo = categoria.grupo_dre if categoria else None
        if grupo in GRUPOS_DRE:
            grupos[grupo] = grupos.get(grupo, Decimal("0")) + valor
        else:
            nome = categoria.nome if categoria else "Sem categoria"
            fora[nome] = fora.get(nome, Decimal("0")) + valor
    return grupos, sorted(fora.items())

def acrescimos_das_quitacoes(data_inicio, data_fim):
    totais = {}
    for prefixo, modelo in (("pagar", FinanceiroPagar), ("receber", FinanceiroReceber)):
        somas = modelo.objects.filter(
            status="pago", data_pagamento__gte=data_inicio, data_pagamento__lte=data_fim
        ).aggregate(juros=Sum("valor_juros"), multa=Sum("valor_multa"), desconto=Sum("valor_desconto"))
        for campo, valor in somas.items():
            totais[f"{prefixo}_{campo}"] = valor or Decimal("0")
    return totais


def dre_por_periodo(data_inicio, data_fim):
    # ============================
    # RECEITA BRUTA
    # ============================
    # Só vendas finalizadas; __date inclui o último dia inteiro do período
    itens = VendaItem.objects.filter(
        venda__status="finalizada",
        venda__data_emissao__date__gte=data_inicio,
        venda__data_emissao__date__lte=data_fim
    ).select_related("produto", "servico", "venda")

    receita_produtos = sum(
        (item.total or 0)
        for item in itens
        if item.produto_id is not None
    )

    receita_servicos = sum(
        (item.total or 0)
        for item in itens
        if item.servico_id is not None
    )

    # Desconto e acréscimo dados na venda inteira (fora dos itens): o acréscimo é receita da venda;
    # o desconto é dedução da receita bruta (desconto incondicional)
    vendas = Venda.objects.filter(
        status="finalizada",
        data_emissao__date__gte=data_inicio,
        data_emissao__date__lte=data_fim,
    ).aggregate(desconto=Sum("desconto"), acrescimo=Sum("acrescimo"))
    descontos_vendas = vendas["desconto"] or Decimal("0")
    receita_acrescimos = vendas["acrescimo"] or Decimal("0")

    receita_bruta = receita_produtos + receita_servicos + receita_acrescimos
    
    # ============================
    # LANÇAMENTOS E TÍTULOS MANUAIS (regime de competência)
    # ============================
    grupos, fora_do_dre = valores_por_grupo_dre(data_inicio, data_fim)
    g = lambda *nomes: sum((grupos.get(n, Decimal("0")) for n in nomes), Decimal("0"))

    receita_outras = g("RECEITA_BRUTA")
    receita_bruta += receita_outras

    icms, iss, pis, cofins = g("ICMS"), g("ISS"), g("PIS"), g("COFINS")
    pis_cofins_juntos = g("PIS_COFINS")
    irpj, csll, irpj_csll_juntos = g("IRPJ"), g("CSLL"), g("IRPJ_CSLL")

    despesas_vendas = g("DESPESA_VENDAS")
    despesas_adm = g("DESPESA_ADM")
    despesas_gerais = g("DESPESA_GERAIS")
    receitas_patrimoniais = g("RECEITA_PATRIMONIAL")
    receitas_financeiras_lancadas = g("RECEITAS_FINANCEIRAS")
    despesas_financeiras_lancadas = g("DESPESAS_FINANCEIRAS")

    # Juros, multa e desconto das quitações, pela data da quitação (é quando ocorrem):
    # pagos e descontos concedidos são despesa financeira; recebidos e descontos obtidos, receita financeira
    acrescimos = acrescimos_das_quitacoes(data_inicio, data_fim)
    juros_multas_pagos = acrescimos["pagar_juros"] + acrescimos["pagar_multa"]
    juros_multas_recebidos = acrescimos["receber_juros"] + acrescimos["receber_multa"]
    descontos_obtidos = acrescimos["pagar_desconto"]
    descontos_concedidos = acrescimos["receber_desconto"]
    receitas_financeiras = receitas_financeiras_lancadas + juros_multas_recebidos + descontos_obtidos
    despesas_financeiras = despesas_financeiras_lancadas + juros_multas_pagos + descontos_concedidos
    # Receitas patrimoniais (ex.: aluguel recebido) não são financeiras: ficam em Outras Receitas
    outras_receitas = receitas_patrimoniais

    # ============================
    # DEDUÇÕES DA RECEITA BRUTA
    # ============================
    deducoes = descontos_vendas + icms + iss + pis + cofins + pis_cofins_juntos
    receita_liquida = receita_bruta - deducoes

    # ============================
    # CMV
    # ============================
    cmv = sum(
        (item.total_cmv or 0)
        for item in CMVItem.objects.filter(
            venda__status="finalizada",
            data__date__gte=data_inicio,
            data__date__lte=data_fim
        )
    )

    # Custos lançados à mão (categorias do grupo Custos, ex.: CSP). O CMV das vendas já vem acima,
    # calculado pelo estoque; a tela avisa para não lançar o mesmo custo de novo
    custos_lancados = g("CUSTOS")
    custo_total = cmv + custos_lancados

    lucro_bruto = receita_liquida - custo_total

    # ============================
    # DESPESAS OPERACIONAIS
    # ============================
    despesas_operacionais = despesas_vendas + despesas_adm + despesas_gerais
    resultado_operacional = lucro_bruto - despesas_operacionais

    # ============================
    # RESULTADO ANTES DO IR
    # ============================
    resultado_antes_ir = resultado_operacional + receitas_financeiras - despesas_financeiras + outras_receitas

    # ============================
    # IR/CSLL (se houver)
    # ============================
    ir_csll = irpj + csll + irpj_csll_juntos
    pis_cofins = pis + cofins + pis_cofins_juntos

    lucro_liquido = resultado_antes_ir - ir_csll

    # ============================
    # RETORNO FINAL
    # ============================
    return {
        "receita_bruta": receita_bruta,
        "receita_produtos": receita_produtos,
        "receita_servicos": receita_servicos,
        "receita_outras": receita_outras,
        "receita_acrescimos": receita_acrescimos,
        "descontos_vendas": descontos_vendas,
        
        "icms": icms,
        "iss": iss,
        "pis": pis,
        "cofins": cofins,
        "pis_cofins_juntos": pis_cofins_juntos,
        "deducoes": deducoes,
        "receita_liquida": receita_liquida,
        
        "cmv": cmv,
        "custos_lancados": custos_lancados,
        "custo_total": custo_total,
        "lucro_bruto": lucro_bruto,
        
        "despesas_vendas": despesas_vendas,
        "despesas_adm": despesas_adm,
        "despesas_gerais": despesas_gerais,
        "despesas_operacionais": despesas_operacionais,
        
        "resultado_operacional": resultado_operacional,
        "receitas_financeiras": receitas_financeiras,
        "despesas_financeiras": despesas_financeiras,
        "outras_receitas": outras_receitas,
        "receitas_patrimoniais": receitas_patrimoniais,
        "receitas_financeiras_lancadas": receitas_financeiras_lancadas,
        "despesas_financeiras_lancadas": despesas_financeiras_lancadas,
        "juros_multas_pagos": juros_multas_pagos,
        "juros_multas_recebidos": juros_multas_recebidos,
        "descontos_obtidos": descontos_obtidos,
        "descontos_concedidos": descontos_concedidos,
        "resultado_antes_ir": resultado_antes_ir,
        
        "irpj": irpj,
        "csll": csll,
        "irpj_csll_juntos": irpj_csll_juntos,
        "ir_csll": ir_csll,
        "pis_cofins": pis_cofins,
        "fora_do_dre": fora_do_dre,
        "lucro_liquido": lucro_liquido,
    }
