from decimal import Decimal
from comercial.models import VendaItem, CMVItem, Venda
from financeiro.models import FinanceiroLancamento

def dre_por_periodo(data_inicio, data_fim):
    # ============================
    # RECEITA BRUTA
    # ============================
    itens = VendaItem.objects.filter(
        venda__data_emissao__gte=data_inicio,
        venda__data_emissao__lte=data_fim
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

    receita_bruta = receita_produtos + receita_servicos
    
    # ============================
    # IMPOSTOS SEPARADOS
    # ============================
    icms = Decimal("0")
    iss = Decimal("0")
    pis = Decimal("0")
    cofins = Decimal("0")
    irpj = Decimal("0")
    csll = Decimal("0")

    # ============================
    # LANÇAMENTOS FINANCEIROS
    # ============================
    lancamentos = FinanceiroLancamento.objects.filter(
        data__gte=data_inicio,
        data__lte=data_fim
    ).select_related("categoria")

    despesas_vendas = Decimal("0")
    despesas_adm = Decimal("0")
    despesas_gerais = Decimal("0")
    outras_receitas = Decimal("0")
    outras_despesas = Decimal("0")

    for lanc in lancamentos:
        cat = lanc.categoria
        if not cat or not cat.grupo_dre:
            continue

        if cat.grupo_dre == "ICMS":
            icms += lanc.valor

        elif cat.grupo_dre == "ISS":
            iss += lanc.valor

        elif cat.grupo_dre == "PIS":
            pis += lanc.valor

        elif cat.grupo_dre == "COFINS":
            cofins += lanc.valor

        elif cat.grupo_dre == "IRPJ":
            irpj += lanc.valor

        elif cat.grupo_dre == "CSLL":
            csll += lanc.valor

        elif cat.grupo_dre == "DESPESA_VENDAS":
            despesas_vendas += lanc.valor

        elif cat.grupo_dre == "DESPESA_ADM":
            despesas_adm += lanc.valor

        elif cat.grupo_dre == "DESPESA_GERAIS":
            despesas_gerais += lanc.valor

        elif cat.grupo_dre == "RECEITAS_PATRIMONIAIS":
            outras_receitas += lanc.valor

        elif cat.grupo_dre == "RECEITAS_FINANCEIRAS":
            outras_receitas += lanc.valor
        
        elif cat.grupo_dre == "DESPESAS_FINANCEIRAS":
            outras_despesas += lanc.valor

    # ============================
    # DEDUÇÕES DA RECEITA BRUTA
    # ============================
    deducoes = icms + iss + pis + cofins
    receita_liquida = receita_bruta - deducoes

    # ============================
    # CMV
    # ============================
    cmv = sum(
        (item.total_cmv or 0)
        for item in CMVItem.objects.filter(
            data__gte=data_inicio,
            data__lte=data_fim
        )
    )

    lucro_bruto = receita_liquida - cmv

    # ============================
    # DESPESAS OPERACIONAIS
    # ============================
    despesas_operacionais = despesas_vendas + despesas_adm + despesas_gerais
    resultado_operacional = lucro_bruto - despesas_operacionais

    # ============================
    # RESULTADO ANTES DO IR
    # ============================
    resultado_antes_ir = resultado_operacional + outras_receitas - outras_despesas

    # ============================
    # IR/CSLL (se houver)
    # ============================
    ir_csll = irpj + csll  # Placeholder para IR/CSLL
    pis_cofins = pis + cofins  # Placeholder para PIS/COFINS

    lucro_liquido = resultado_antes_ir - ir_csll

    # ============================
    # RETORNO FINAL
    # ============================
    return {
        "receita_bruta": receita_bruta,
        "receita_produtos": receita_produtos,
        "receita_servicos": receita_servicos,
        
        "icms": icms,
        "iss": iss,
        "pis": pis,
        "cofins": cofins,
        "deducoes": deducoes,
        "receita_liquida": receita_liquida,
        
        "cmv": cmv,
        "lucro_bruto": lucro_bruto,
        
        "despesas_vendas": despesas_vendas,
        "despesas_adm": despesas_adm,
        "despesas_gerais": despesas_gerais,
        "despesas_operacionais": despesas_operacionais,
        
        "resultado_operacional": resultado_operacional,
        "outras_receitas": outras_receitas,
        "outras_despesas": outras_despesas,
        "resultado_antes_ir": resultado_antes_ir,
        
        "ir_csll": ir_csll,
        "pis_cofins": pis_cofins,  # Placeholder para PIS/COFINS
        "lucro_liquido": lucro_liquido,
    }
