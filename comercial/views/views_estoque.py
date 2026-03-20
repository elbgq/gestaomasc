# Import para views genéricas do Django para compras, vendas e estoque
from django.views.generic import ListView
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from cadastros.models import Produto
from comercial.models import MovimentacaoEstoque, Estoque, Venda, CMVItem
from django.db.models import Sum
from datetime import datetime

#====================================
# ESTOQUE
#====================================

# Views para Estoque "REVISADO"
class EstoqueListView(ListView):
    model = Estoque
    template_name = 'comercial/estoque_list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q")

        if q:
            qs = qs.filter(produto__descricao__icontains=q)

        return qs
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        params = self.request.GET.copy()
        params.pop("page", None)  # Remove o parâmetro de paginação para manter os filtros ao navegar

        context["params"] = params.urlencode()

        return context

# Movimentações de estoque podem ser adicionadas aqui conforme necessário "REVISADO"
class MovimentacaoEstoqueListView(ListView):
    model = MovimentacaoEstoque
    template_name = 'comercial/movimentacao_list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()

        ordenar = self.request.GET.get("ordenar", "-data")

        # Segurança: evita erros se o parâmetro for inválido
        campos_validos = [
            "data", "-data",
            "produto__descricao", "-produto__descricao",
            "produto__codor", "-produto__codor",
            "quantidade", "-quantidade",
            "preco", "-preco",
            "saldo_apos", "-saldo_apos",
            "preco_medio_apos", "-preco_medio_apos",
        ]

        if ordenar in campos_validos:
            qs = qs.order_by(ordenar)

        return qs

#======================================
# Relatório de Movimentação de estoque
#======================================
def relatorio_estoque(request):
    produtos = Produto.objects.all()
 
    produto_id = request.GET.get("produto")
    data_inicio = request.GET.get("inicio")
    data_fim = request.GET.get("fim")

    movimentacoes = MovimentacaoEstoque.objects.all().order_by("-data")

    # Filtro por produto
    if produto_id:
        movimentacoes = movimentacoes.filter(produto_id=produto_id)

    # Filtro por período
    if data_inicio:
        movimentacoes = movimentacoes.filter(data__gte=data_inicio)
    if data_fim:
        movimentacoes = movimentacoes.filter(data__lte=data_fim)

    # Saldo inicial antes do período
    saldo_inicial = None
    preco_medio_inicial = None

    if produto_id and data_inicio:
        mov_antes = MovimentacaoEstoque.objects.filter(
            produto_id=produto_id,
            data__lt=data_inicio
        ).order_by("-data").first()

        if mov_antes:
            saldo_inicial = mov_antes.saldo_apos
            preco_medio_inicial = mov_antes.preco_medio_apos

    # Totais do período
    total_entradas = movimentacoes.filter(tipo="ENTRADA").aggregate(
        total=Sum("quantidade")
    )["total"] or 0

    total_saidas = movimentacoes.filter(tipo="SAIDA").aggregate(
        total=Sum("quantidade")
    )["total"] or 0

    # Saldo final
    saldo_final = None
    preco_medio_final = None

    if movimentacoes.exists():
        ultimo = movimentacoes.last()
        saldo_final = ultimo.saldo_apos
        preco_medio_final = ultimo.preco_medio_apos

    contexto = {
        "produtos": produtos,
        "movimentacoes": movimentacoes,
        "saldo_inicial": saldo_inicial,
        "preco_medio_inicial": preco_medio_inicial,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "saldo_final": saldo_final,
        "preco_medio_final": preco_medio_final,
    }

    return render(request, "comercial/estoque_relatorio.html", contexto)

# Relatório de estoque "REVISADO"
def estoque_relatorio(request):
    filtro = request.GET.get("filtro", "todos")

    qs = Estoque.objects.select_related("produto")

    if filtro == "zerado":
        qs = qs.filter(quantidade=0)

    elif filtro == "baixo":
        qs = qs.filter(quantidade__lt=models.F("produto__estoque_minimo"))

    elif filtro == "negativo":
        qs = qs.filter(quantidade__lt=0)

    context = {
        "estoques": qs,
        "filtro": filtro
    }
    return render(request, "comercial/estoque_relatorio.html", context)


# AJAX endpoint para consultar estoque de um produto "REVISADO"
def ajax_estoque(request, produto_id):
    try:
        produto = Produto.objects.get(id=produto_id)
        estoque = Estoque.objects.filter(produto=produto).first()
        quantidade = estoque.quantidade if estoque else 0
        return JsonResponse({"estoque": quantidade})
    except Produto.DoesNotExist:
        return JsonResponse({
            "estoque": float(quantidade),
            "preco_medio": float(estoque.preco_medio if estoque else 0)
        })
     
# Função auxiliar para baixa de estoque após venda "REVISADA"
"""
    Registra movimentações de estoque (SAÍDA) para cada item de produto
    e calcula o CMV total da venda.
"""
def registrar_cmv(venda):
    cmv_total = Decimal("0.00")

    # IDs dos itens da venda
    itens_ids = venda.itens.values_list("id", flat=True)

    # 1. Estornar CMV antigo
    CMVItem.objects.filter(item_id__in=itens_ids).delete()

    # 2. Registrar novas movimentações e calcular CMV
    for item in venda.itens.all():
        # Serviços não têm CMV
        if not item.produto:
            continue # serviços não têm CMV
        
        # Registrar saída no estoque
        mov = MovimentacaoEstoque.objects.create(
            produto=item.produto,
            tipo="SAIDA",
            quantidade=item.quantidade,
            preco=None,
            origem="VENDA",
            referencia_id=item.id
        )

        # Criar registro de CMV congelado
        cmv_item = CMVItem.objects.create(
            venda=venda,
            item=item,
            produto=item.produto,
            quantidade=item.quantidade,
            custo_medio=mov.preco_medio_apos,
            total_cmv=mov.preco_medio_apos * item.quantidade,
            data=venda.data_emissao
        )

        # CMV do item
        cmv_total += cmv_item.total_cmv
        
    # Atualiza venda
    
    venda.cmv = cmv_total
    venda.lucro_bruto = venda.total - venda.cmv
    venda.save()

#====================================
# CMV detalhado
#====================================
def cmv_lista(request):
    vendas = Venda.objects.all().order_by("-data_emissao")
    return render(request, "comercial/cmv_lista.html", {"vendas": vendas})


def cmv_detalhe(request, venda_id):
    venda = get_object_or_404(Venda, id=venda_id)

    itens_cmv = CMVItem.objects.filter(venda=venda).select_related("produto", "item")

    total_quantidade = sum(i.quantidade for i in itens_cmv)
    total_cmv = sum(i.total_cmv for i in itens_cmv)

    contexto = {
        "venda": venda,
        "itens": itens_cmv,
        "total_quantidade": total_quantidade,
        "total_cmv": total_cmv,
    }

    return render(request, "comercial/cmv_detalhe.html", contexto)
    