# relatorios/services/painel.py
#
# Números do Painel (tela inicial). Uma função por bloco; a tela só chama as dos blocos
# que o usuário pode ver. As contas são feitas no banco (Sum/Count), uma consulta por indicador.
from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Min, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncMonth

from cadastros.models import Contato, Produto
from cadastros.precos import produtos_sinalizados
from comercial.models import (CMVItem, Compra, CompraItem, Estoque, MetaFaturamento, MovimentacaoEstoque, PosVenda,
                               Venda, VendaItem)
from financeiro.models import CaixaMovimento, Caixa, FinanceiroPagar, FinanceiroReceber
from relatorios.services.dre_service import dre_por_periodo

ZERO = Decimal("0.00")
DINHEIRO = DecimalField(max_digits=14, decimal_places=2)
CACHE_SEGUNDOS = 300
DIAS_PARADO = 90
DIAS_PROJECAO = 90
DIAS_ATIVO = 90
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

PERIODOS = [
    ("hoje", "Hoje"),
    ("7dias", "7 dias"),
    ("mes", "Mês"),
    ("mes_anterior", "Mês anterior"),
    ("12meses", "12 meses"),
]


# ---------------- Período ----------------

def _inicio_do_mes(d, meses_atras=0):
    ano, mes = divmod(d.year * 12 + d.month - 1 - meses_atras, 12)
    return date(ano, mes + 1, 1)


def _fim_do_mes(d):
    return _inicio_do_mes(d, -1) - timedelta(days=1)


# Devolve o período escolhido e o período anterior de mesmo tamanho, para comparar
def periodo(codigo, hoje):
    if codigo == "hoje":
        ini, fim = hoje, hoje
        ant = (hoje - timedelta(days=1), hoje - timedelta(days=1))
    elif codigo == "7dias":
        ini, fim = hoje - timedelta(days=6), hoje
        ant = (hoje - timedelta(days=13), hoje - timedelta(days=7))
    elif codigo == "mes_anterior":
        ini = _inicio_do_mes(hoje, 1)
        fim = _fim_do_mes(ini)
        ant = (_inicio_do_mes(hoje, 2), ini - timedelta(days=1))
    elif codigo == "12meses":
        ini, fim = _inicio_do_mes(hoje, 11), hoje
        ant = (_inicio_do_mes(hoje, 23), ini - timedelta(days=1))
    else:
        codigo = "mes"
        ini, fim = _inicio_do_mes(hoje), hoje
        # Mês anterior até o mesmo dia (ou até o último dia, se o mês for mais curto)
        ini_ant = _inicio_do_mes(hoje, 1)
        ant = (ini_ant, min(ini_ant + timedelta(days=hoje.day - 1), _fim_do_mes(ini_ant)))
    return {"codigo": codigo, "ini": ini, "fim": fim, "ini_ant": ant[0], "fim_ant": ant[1]}


def variacao(atual, anterior):
    # Variação em % contra o período anterior; None quando não há base para comparar
    atual, anterior = Decimal(atual or 0), Decimal(anterior or 0)
    if anterior == 0:
        return None
    return ((atual - anterior) / anterior * 100).quantize(Decimal("0.1"))


def em_cache(chave, calcular, atualizar=False):
    # Guarda o bloco por 5 minutos; "atualizar" recalcula na hora
    dados = None if atualizar else cache.get(chave)
    if dados is None:
        dados = calcular()
        cache.set(chave, dados, CACHE_SEGUNDOS)
    return dados


# ---------------- Vendas ----------------

def _vendas(ini, fim):
    return Venda.objects.filter(status="finalizada", data_emissao__date__gte=ini, data_emissao__date__lte=fim)


def _serie_vendas(per):
    # Faturamento por dia (por mês no período de 12 meses), com o período anterior alinhado ao lado
    ini, fim, ini_ant, fim_ant = per["ini"], per["fim"], per["ini_ant"], per["fim_ant"]
    if per["codigo"] == "12meses":
        trunc, passos = TruncMonth, [_inicio_do_mes(fim, 11 - i) for i in range(12)]
        passos_ant = [_inicio_do_mes(ini_ant, -i) for i in range(12)]
        rotulo = lambda d: f"{MESES_PT[d.month - 1]}/{d.year % 100:02d}"
    else:
        # Hoje sozinho não forma linha: mostra a semana
        if (fim - ini).days < 6:
            ini, ini_ant, fim_ant = fim - timedelta(days=6), fim - timedelta(days=13), fim - timedelta(days=7)
        dias = (fim - ini).days + 1
        trunc, passos = TruncDate, [ini + timedelta(days=i) for i in range(dias)]
        passos_ant = [ini_ant + timedelta(days=i) for i in range(dias)]
        rotulo = lambda d: d.strftime("%d/%m")

    def somas(de, ate):
        linhas = (_vendas(de, ate).annotate(p=trunc("data_emissao")).values("p")
                  .annotate(t=Sum("total")).values_list("p", "t"))
        return {(p.date() if hasattr(p, "date") else p): t for p, t in linhas}

    atual = somas(passos[0], fim)
    anterior = somas(ini_ant, fim_ant)
    return {
        "rotulos": [rotulo(d) for d in passos],
        "atual": [float(atual.get(d) or 0) for d in passos],
        # Mês anterior mais curto: os dias que ele não tem ficam sem ponto
        "anterior": [float(anterior.get(d) or 0) if d <= fim_ant else None for d in passos_ant],
    }


def bloco_vendas(per, ver_custos):
    vendas = _vendas(per["ini"], per["fim"])
    agora = vendas.aggregate(fat=Sum("total"), qtd=Count("id"), desconto=Sum("desconto"))
    antes = _vendas(per["ini_ant"], per["fim_ant"]).aggregate(fat=Sum("total"), qtd=Count("id"))

    faturamento = agora["fat"] or ZERO
    qtd = agora["qtd"]
    ticket = (faturamento / qtd).quantize(Decimal("0.01")) if qtd else ZERO
    ticket_ant = ((antes["fat"] or ZERO) / antes["qtd"]) if antes["qtd"] else ZERO

    valor_item = ExpressionWrapper(F("quantidade") * F("preco_unitario") - F("desconto"), output_field=DINHEIRO)
    itens = VendaItem.objects.filter(venda__in=vendas)
    tipos = itens.aggregate(
        produtos=Sum(valor_item, filter=Q(produto__isnull=False)),
        servicos=Sum(valor_item, filter=Q(servico__isnull=False)),
        desconto_itens=Sum("desconto"),
    )
    top_itens = [
        {"nome": linha["produto__descricao"] or linha["servico__descricao"], "total": linha["total"]}
        for linha in itens.values("produto__descricao", "servico__descricao")
        .annotate(total=Sum(valor_item)).order_by("-total")[:10]
    ]

    nomes_forma = dict(Venda.PAGAR_CHOICES)
    formas = [
        {"nome": nomes_forma.get(linha["forma_pagamento"], "Não informada"), "total": linha["total"]}
        for linha in vendas.values("forma_pagamento").annotate(total=Sum("total")).order_by("-total")
    ]
    vendedores = [
        {"nome": linha["vendedor__nome"] or "Sem vendedor", "total": linha["total"], "qtd": linha["qtd"]}
        for linha in vendas.values("vendedor__nome").annotate(total=Sum("total"), qtd=Count("id")).order_by("-total")
    ]

    dados = {
        "faturamento": faturamento,
        "faturamento_var": variacao(faturamento, antes["fat"]),
        "qtd": qtd,
        "qtd_var": variacao(qtd, antes["qtd"]),
        "ticket": ticket,
        "ticket_var": variacao(ticket, ticket_ant),
        "descontos": (agora["desconto"] or ZERO) + (tipos["desconto_itens"] or ZERO),
        "rascunhos": Venda.objects.filter(status="rascunho").count(),
        "produtos": tipos["produtos"] or ZERO,
        "servicos": tipos["servicos"] or ZERO,
        "top_itens": top_itens,
        "formas": formas,
        "vendedores": vendedores,
        "serie": _serie_vendas(per),
    }
    if ver_custos:
        # Mesmo CMV da DRE (itens de CMV das vendas finalizadas do período)
        cmv = CMVItem.objects.filter(venda__in=vendas).aggregate(t=Sum("total_cmv"))["t"] or ZERO
        dados["cmv"] = cmv
        dados["margem"] = faturamento - cmv
        dados["margem_pct"] = ((faturamento - cmv) / faturamento * 100).quantize(Decimal("0.1")) if faturamento else None
    return dados


# Meta de faturamento: a do mês atual (a do mês anterior, se esse for o período escolhido)
def bloco_meta(per, hoje):
    mes = per["ini"] if per["codigo"] == "mes_anterior" else _inicio_do_mes(hoje)
    meta = MetaFaturamento.objects.filter(mes=mes).first()
    if not meta:
        return {"mes": mes, "valor": None}
    fim_mes = _fim_do_mes(mes)
    ate = min(fim_mes, hoje)
    realizado = _vendas(mes, ate).aggregate(t=Sum("total"))["t"] or ZERO
    dados = {
        "mes": mes,
        "valor": meta.valor,
        "realizado": realizado,
        "pct": (realizado / meta.valor * 100).quantize(Decimal("0.1")) if meta.valor else None,
        "falta": max(meta.valor - realizado, ZERO),
        "fechado": ate == fim_mes and hoje > fim_mes,
    }
    if not dados["fechado"]:
        # Projeção no ritmo do mês até hoje; o que falta vender por dia conta hoje como dia restante
        dias_mes, passados = fim_mes.day, hoje.day
        dados["projecao"] = (realizado / passados * dias_mes).quantize(Decimal("0.01"))
        dados["projecao_pct"] = (dados["projecao"] / meta.valor * 100).quantize(Decimal("0.1")) if meta.valor else None
        dados["por_dia"] = (dados["falta"] / (dias_mes - passados + 1)).quantize(Decimal("0.01"))
        dados["dias_restantes"] = dias_mes - passados + 1
    return dados


# ---------------- Estoque ----------------

def bloco_estoque(per, hoje, ver_custos):
    valor_linha = ExpressionWrapper(F("quantidade") * F("preco_medio"), output_field=DINHEIRO)

    abaixo = (
        Produto.objects.filter(estoque_minimo__gt=0)
        .annotate(saldo=Coalesce(Sum("estoque__quantidade"), Value(Decimal("0")), output_field=DINHEIRO))
        .filter(saldo__lt=F("estoque_minimo"))
        .order_by("saldo", "descricao")
    )

    # Parado: tem saldo e nenhuma movimentação (compra, venda ou ajuste) nos últimos 90 dias
    limite = hoje - timedelta(days=DIAS_PARADO)
    ultima_mov = (MovimentacaoEstoque.objects.filter(produto=OuterRef("produto"))
                  .values("produto").annotate(m=Max("data")).values("m"))
    parados = (
        Estoque.objects.filter(quantidade__gt=0)
        .annotate(ultima=Subquery(ultima_mov), valor=valor_linha)
        .filter(Q(ultima__date__lt=limite) | Q(ultima__isnull=True))
        .select_related("produto")
        .order_by("-valor" if ver_custos else "-quantidade")
    )
    parados_resumo = parados.aggregate(qtd=Count("id"), total=Sum(valor_linha))

    compras = Compra.objects.filter(confirmada=True, data__gte=per["ini"], data__lte=per["fim"])
    compras_ant = Compra.objects.filter(confirmada=True, data__gte=per["ini_ant"], data__lte=per["fim_ant"])
    total_compras = compras.aggregate(t=Sum("valor_total"))["t"] or ZERO

    dados = {
        "abaixo_qtd": abaixo.count(),
        "abaixo": [{"produto": p, "saldo": p.saldo, "minimo": p.estoque_minimo} for p in abaixo[:10]],
        "zerados": Estoque.objects.filter(quantidade__lte=0).count(),
        "parados_qtd": parados_resumo["qtd"],
        "parados": [
            {"produto": e.produto, "quantidade": e.quantidade, "valor": e.valor, "ultima": e.ultima}
            for e in parados[:10]
        ],
        "compras": total_compras,
        "compras_qtd": compras.count(),
        "compras_var": variacao(total_compras, compras_ant.aggregate(t=Sum("valor_total"))["t"]),
        "compras_pendentes": Compra.objects.filter(confirmada=False).count(),
        "itens_sem_vinculo": CompraItem.objects.filter(status="pendente").count(),
    }
    if ver_custos:
        valor = Estoque.objects.filter(quantidade__gt=0).aggregate(v=Sum(valor_linha))["v"] or ZERO
        # Cobertura: quantos dias o estoque atual dura no ritmo de saída (CMV) dos últimos 90 dias
        cmv_90 = CMVItem.objects.filter(
            venda__status="finalizada", venda__data_emissao__date__gt=hoje - timedelta(days=90)
        ).aggregate(t=Sum("total_cmv"))["t"] or ZERO
        dados["valor"] = valor
        dados["cobertura_dias"] = int(valor / (cmv_90 / 90)) if cmv_90 > 0 else None
        dados["parados_valor"] = parados_resumo["total"] or ZERO
        dados["precos_revisar"] = len(produtos_sinalizados(Produto.objects.prefetch_related("estoque_set")))
    return dados


# ---------------- Financeiro (aproveita o antigo Dashboard Financeiro) ----------------

def bloco_financeiro(hoje):
    caixas = [{"nome": c.nome, "saldo": c.saldo_atual()} for c in Caixa.objects.filter(ativo=True).order_by("nome")]

    def pendentes(modelo):
        return modelo.objects.filter(status="pendente")

    def soma(qs):
        r = qs.aggregate(t=Sum("valor"), n=Count("id"))
        return r["t"] or ZERO, r["n"]

    em_30 = (hoje, hoje + timedelta(days=30))
    receber_30, receber_30_n = soma(pendentes(FinanceiroReceber).filter(data_vencimento__range=em_30))
    pagar_30, pagar_30_n = soma(pendentes(FinanceiroPagar).filter(data_vencimento__range=em_30))
    receber_venc, receber_venc_n = soma(pendentes(FinanceiroReceber).filter(data_vencimento__lt=hoje))
    pagar_venc, pagar_venc_n = soma(pendentes(FinanceiroPagar).filter(data_vencimento__lt=hoje))

    def lista(filtro, limite=10):
        # Receber e pagar juntos, por vencimento
        linhas = [
            {"tipo": "R", "id": t.id, "nome": t.cliente.nome, "descricao": t.descricao,
             "valor": t.valor, "vencimento": t.data_vencimento}
            for t in pendentes(FinanceiroReceber).filter(**filtro).select_related("cliente").order_by("data_vencimento")[:limite]
        ] + [
            {"tipo": "D", "id": t.id, "nome": t.contato.nome if t.contato else "", "descricao": t.descricao,
             "valor": t.valor, "vencimento": t.data_vencimento}
            for t in pendentes(FinanceiroPagar).filter(**filtro).select_related("contato").order_by("data_vencimento")[:limite]
        ]
        return sorted(linhas, key=lambda t: t["vencimento"])[:limite]

    # Entradas x saídas do caixa nos últimos 6 meses (o gráfico do dashboard antigo, numa consulta só)
    meses = [_inicio_do_mes(hoje, 5 - i) for i in range(6)]
    movimentos = (CaixaMovimento.objects.filter(data__gte=meses[0], data__lte=hoje)
                  .annotate(m=TruncMonth("data")).values("m", "tipo").annotate(t=Sum("valor")))
    por_mes = {(m["m"], m["tipo"]): m["t"] for m in movimentos}

    saldo = sum((c["saldo"] for c in caixas), ZERO)
    return {
        "caixas": caixas,
        "saldo": saldo,
        "fluxo": fluxo_projetado(hoje, saldo),
        "receber_30": receber_30, "receber_30_n": receber_30_n,
        "pagar_30": pagar_30, "pagar_30_n": pagar_30_n,
        "receber_vencido": receber_venc, "receber_vencido_n": receber_venc_n,
        "pagar_vencido": pagar_venc, "pagar_vencido_n": pagar_venc_n,
        "vencidos": lista({"data_vencimento__lt": hoje}),
        "proximos": lista({"data_vencimento__range": (hoje, hoje + timedelta(days=7))}),
        "grafico": {
            "rotulos": [f"{MESES_PT[m.month - 1]}/{m.year % 100:02d}" for m in meses],
            "entradas": [float(por_mes.get((m, "E")) or 0) for m in meses],
            "saidas": [float(por_mes.get((m, "S")) or 0) for m in meses],
        },
    }


# Fluxo de caixa projetado: saldo de hoje + o que vence a receber - o que vence a pagar, dia a dia.
# Só títulos pendentes com vencimento de hoje em diante; os vencidos ficam fora (aparecem nos cartões).
def fluxo_projetado(hoje, saldo, dias=DIAS_PROJECAO):
    fim = hoje + timedelta(days=dias)

    def por_dia(modelo):
        linhas = (modelo.objects.filter(status="pendente", data_vencimento__range=(hoje, fim))
                  .values("data_vencimento").annotate(t=Sum("valor")).values_list("data_vencimento", "t"))
        return dict(linhas)

    entradas, saidas = por_dia(FinanceiroReceber), por_dia(FinanceiroPagar)
    rotulos, saldos, faixas = [], [], []
    marcos = {30, 60, 90}
    atual, soma_e, soma_s = saldo, ZERO, ZERO
    menor = {"saldo": saldo, "data": hoje}
    for i in range(dias + 1):
        d = hoje + timedelta(days=i)
        e, s = entradas.get(d) or ZERO, saidas.get(d) or ZERO
        atual, soma_e, soma_s = atual + e - s, soma_e + e, soma_s + s
        rotulos.append(d.strftime("%d/%m"))
        saldos.append(float(atual))
        if atual < menor["saldo"]:
            menor = {"saldo": atual, "data": d}
        if i in marcos:
            faixas.append({"dias": i, "ate": d, "entradas": soma_e, "saidas": soma_s, "saldo": atual})
    return {
        "faixas": faixas,
        "menor": menor,
        # Primeiro dia em que o saldo previsto fica negativo (None se não fica)
        "negativo_em": next((hoje + timedelta(days=i) for i, v in enumerate(saldos) if v < 0), None),
        "grafico": {"rotulos": rotulos, "saldo": saldos},
    }


# ---------------- Resultado do período (mesmas contas da DRE) ----------------

RESULTADO = ["receita_liquida", "lucro_bruto", "despesas_operacionais", "lucro_liquido"]


def bloco_resultado(per):
    agora = dre_por_periodo(per["ini"], per["fim"])
    antes = dre_por_periodo(per["ini_ant"], per["fim_ant"])
    dados = {campo: agora[campo] for campo in RESULTADO}
    dados.update({f"{campo}_var": variacao(agora[campo], antes[campo]) for campo in RESULTADO})
    # Variação de lucro sobre base negativa engana (prejuízo menor daria queda): só compara base positiva
    for campo in ("lucro_bruto", "lucro_liquido"):
        if antes[campo] <= 0:
            dados[f"{campo}_var"] = None
    receita = agora["receita_liquida"]
    dados["margem_liquida"] = (agora["lucro_liquido"] / receita * 100).quantize(Decimal("0.1")) if receita else None
    dados["lucro_liquido_negativo"] = agora["lucro_liquido"] < 0
    dados["fora_do_dre"] = len(agora["fora_do_dre"])
    return dados


# ---------------- Clientes ----------------

def bloco_clientes(per, hoje):
    finalizadas = Venda.objects.filter(status="finalizada")

    def clientes_entre(ini, fim):
        return set(finalizadas.filter(data_emissao__date__gte=ini, data_emissao__date__lte=fim)
                   .values_list("cliente_id", flat=True))

    # Primeira e última compra de cada cliente (o cadastro não guarda data de criação)
    historico = {
        linha["cliente_id"]: linha
        for linha in finalizadas.values("cliente_id").annotate(
            primeira=Min("data_emissao"), ultima=Max("data_emissao"), qtd=Count("id"), total=Sum("total"))
    }
    data = lambda dt: timezone.localdate(dt)

    def novos_entre(ini, fim):
        return sum(1 for h in historico.values() if ini <= data(h["primeira"]) <= fim)

    do_periodo = clientes_entre(per["ini"], per["fim"])
    do_anterior = clientes_entre(per["ini_ant"], per["fim_ant"])
    novos, novos_ant = novos_entre(per["ini"], per["fim"]), novos_entre(per["ini_ant"], per["fim_ant"])

    # Recompra: clientes do período que já compraram mais de uma vez (no período ou antes dele)
    ate_fim = dict(finalizadas.filter(data_emissao__date__lte=per["fim"], cliente_id__in=do_periodo)
                   .values("cliente_id").annotate(n=Count("id")).values_list("cliente_id", "n"))
    recompra = sum(1 for n in ate_fim.values() if n >= 2)

    # Parados: compravam e não compram há 90 dias; os que mais compraram primeiro, para ligar
    limite = hoje - timedelta(days=DIAS_ATIVO)
    ids_parados = [c for c, h in historico.items() if data(h["ultima"]) < limite]
    contatos = Contato.objects.in_bulk(ids_parados + list(do_periodo))
    parados = sorted(
        ({"cliente": contatos[c], "ultima": data(historico[c]["ultima"]), "qtd": historico[c]["qtd"],
          "total": historico[c]["total"] or ZERO} for c in ids_parados),
        key=lambda p: -p["total"],
    )

    # Curva ABC do período: quanto cada cliente faturou e a soma acumulada
    por_cliente = list(_vendas(per["ini"], per["fim"]).values("cliente_id").annotate(total=Sum("total")).order_by("-total"))
    faturamento = sum((linha["total"] or ZERO for linha in por_cliente), ZERO)
    abc, acumulado, classes = [], ZERO, {"A": 0, "B": 0, "C": 0}
    for linha in por_cliente:
        antes = acumulado / faturamento * 100 if faturamento else ZERO
        acumulado += linha["total"] or ZERO
        # Classe pelo acumulado antes do cliente: A até 80%, B até 95%, C o resto
        classe = "A" if antes < 80 else "B" if antes < 95 else "C"
        classes[classe] += 1
        abc.append({"cliente": contatos[linha["cliente_id"]], "total": linha["total"], "classe": classe,
                    "pct": (linha["total"] / faturamento * 100).quantize(Decimal("0.1")) if faturamento else None})
    top10 = sum((linha["total"] for linha in abc[:10]), ZERO)

    # Inadimplência: vencido sobre o total em aberto, e quem mais deve
    aberto = FinanceiroReceber.objects.filter(status="pendente")
    somas = aberto.aggregate(total=Sum("valor"), vencido=Sum("valor", filter=Q(data_vencimento__lt=hoje)))
    total_aberto, vencido = somas["total"] or ZERO, somas["vencido"] or ZERO
    devedores = [
        {"cliente_id": linha["cliente_id"], "nome": linha["cliente__nome"], "telefone": linha["cliente__telefone"],
         "total": linha["total"], "qtd": linha["qtd"], "desde": linha["desde"], "dias": (hoje - linha["desde"]).days}
        for linha in aberto.filter(data_vencimento__lt=hoje)
        .values("cliente_id", "cliente__nome", "cliente__telefone")
        .annotate(total=Sum("valor"), qtd=Count("id"), desde=Min("data_vencimento")).order_by("-total")[:5]
    ]

    # Atraso médio dos títulos recebidos no período (pagos em dia contam zero)
    pagos = (FinanceiroReceber.objects.filter(status="pago", data_pagamento__gte=per["ini"], data_pagamento__lte=per["fim"])
             .values_list("data_vencimento", "data_pagamento"))
    atrasos = [max((pag - venc).days, 0) for venc, pag in pagos]

    # Pós-venda: o que está aberto, o que passou da data de retorno e o que foi registrado no período
    abertos = PosVenda.objects.filter(status="aberto")
    nomes_tipo = dict(PosVenda.TIPO_CHOICES)
    pos_venda = {
        "abertos": abertos.count(),
        "atrasados": abertos.filter(retorno__lt=hoje).count(),
        "lista": list(abertos.select_related("cliente").order_by(F("retorno").asc(nulls_last=True), "data")[:8]),
        "no_periodo": [
            {"tipo": nomes_tipo.get(linha["tipo"], linha["tipo"]), "qtd": linha["qtd"]}
            for linha in PosVenda.objects.filter(data__gte=per["ini"], data__lte=per["fim"])
            .values("tipo").annotate(qtd=Count("id")).order_by("-qtd")
        ],
        "resolvidos_no_periodo": PosVenda.objects.filter(resolvido_em__gte=per["ini"], resolvido_em__lte=per["fim"]).count(),
    }

    return {
        "pos_venda": pos_venda,
        "ativos": len(set(finalizadas.filter(data_emissao__date__gt=limite).values_list("cliente_id", flat=True))),
        "do_periodo": len(do_periodo),
        "do_periodo_var": variacao(len(do_periodo), len(do_anterior)),
        "novos": novos,
        "novos_var": variacao(novos, novos_ant),
        "recompra": recompra,
        "recompra_pct": (Decimal(recompra) / len(do_periodo) * 100).quantize(Decimal("0.1")) if do_periodo else None,
        "parados_qtd": len(parados),
        "parados": parados[:10],
        "abc": abc[:10],
        "abc_classes": classes,
        "abc_qtd": len(abc),
        "top10_pct": (top10 / faturamento * 100).quantize(Decimal("0.1")) if faturamento else None,
        "inad_aberto": total_aberto,
        "inad_vencido": vencido,
        "inad_pct": (vencido / total_aberto * 100).quantize(Decimal("0.1")) if total_aberto else None,
        "devedores": devedores,
        "atraso_medio": (Decimal(sum(atrasos)) / len(atrasos)).quantize(Decimal("0.1")) if atrasos else None,
        "em_dia_pct": (Decimal(sum(1 for a in atrasos if a == 0)) / len(atrasos) * 100).quantize(Decimal("0.1")) if atrasos else None,
        "recebidos_qtd": len(atrasos),
    }
