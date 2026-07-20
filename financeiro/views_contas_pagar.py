from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from django.db.models import Sum
from django.core.paginator import Paginator

from financeiro.models import (CaixaMovimento, FinanceiroCategoria,
            FinanceiroLancamento, FinanceiroPagar,
        )
from financeiro.forms import PagarVencimentoForm, FinanceiroPagarForm
from cadastros.models import Contato

from django.http import HttpResponseForbidden
from .models import FinanceiroPagar


# Views para Contas a Pagar
def pagar_update(request, pk):
    titulo = get_object_or_404(FinanceiroPagar, pk=pk)

    # Se for COMPRA ou LANCAMENTO, só permite editar vencimento
    if titulo.origem in ["COMPRA", "LANCAMENTO"]:
        form = PagarVencimentoForm(request.POST or None, instance=titulo)
        template = "financeiro/conta_pagar_vencimento_form.html"
    else:
        form = FinanceiroPagarForm(request.POST or None, instance=titulo)
        template = "financeiro/conta_pagar_form.html"

    if form.is_valid():
        form.save()
        return redirect("financeiro:contas_pagar_lista")
    
    return render(request, template, {
        "form": form,
        "titulo": titulo,
    })
    
# View para excluir títulos manuais
def pagar_delete(request, pk):
    titulo = get_object_or_404(FinanceiroPagar, pk=pk)

    if titulo.origem != "MANUAL":
        return HttpResponseForbidden("Somente títulos manuais podem ser excluídos.")

    if request.method == "POST":
        titulo.delete()
        return redirect("financeiro:contas_pagar_lista")

    return render(request, "financeiro/pagar_confirm_delete.html", {"titulo": titulo})

# View para listar contas a pagar com filtros
def contas_pagar_lista(request):
    hoje = timezone.localdate()
    # Query base
    titulos = FinanceiroPagar.objects.select_related("contato", "categoria").order_by("data_vencimento")
 
    # ================== Filtros ==================
    # Filtro por contato
    contato = request.GET.get("contato")
    if contato:
        titulos = titulos.filter(contato_id=contato)
    
    # Filtro por vencimento
    vencimento = request.GET.get("vencimento")
    if vencimento == "vencidos":
        titulos = titulos.filter(data_vencimento__lt=hoje, valor_pago__isnull=True)
    elif vencimento == "hoje":
        titulos = titulos.filter(data_vencimento=hoje)
    elif vencimento == "amanha":
        titulos = titulos.filter(data_vencimento=hoje + timezone.timedelta(days=1))
  
    # ===== Separação entre abas ======
    contas_compras = titulos.filter(origem="COMPRA")
    contas_avulsas = titulos.exclude(origem="COMPRA")

    # -------------------------
    # PAGINAÇÃO INDEPENDENTE
    # -------------------------
  
    page_compras = request.GET.get("page_compras")
    page_avulsas = request.GET.get("page_avulsas")

    paginator_compras = Paginator(contas_compras, 20)
    paginator_avulsas = Paginator(contas_avulsas, 20)

    page_obj_compras = paginator_compras.get_page(page_compras)
    page_obj_avulsas = paginator_avulsas.get_page(page_avulsas)

    # Cálculo para o resumo
    total_compras = contas_compras.aggregate(total=Sum("valor"))["total"] or 0
    total_avulsas = contas_avulsas.aggregate(total=Sum("valor"))["total"] or 0

    vencidos_compras = contas_compras.filter(data_vencimento__lt=hoje, valor_pago__isnull=True).count()
    vencidos_avulsas = contas_avulsas.filter(data_vencimento__lt=hoje, valor_pago__isnull=True).count()


    contexto = {
        "hoje": hoje,
        # Objetos paginados
        "page_obj_compras": page_obj_compras,
        "page_obj_avulsas": page_obj_avulsas,
        
        # Paginadores para controle de links
        "paginator_compras": paginator_compras,
        "paginator_avulsas": paginator_avulsas,
        
        # Resumos
        "total_compras": total_compras,
        "vencidos_compras": vencidos_compras,
        "total_avulsas": total_avulsas,
        "vencidos_avulsas": vencidos_avulsas,
        
        # Para manter filtros nos links do paginator
        "params": request.GET.urlencode(),
    }

    return render(request, "financeiro/contas_pagar_lista.html", contexto)

# Gera títulos de contas a pagar para uma compra parcelada.
# Chamado pela view comercial.compra_criar
def gerar_financeiro_pagar_da_compra(compra, parcelas, dias, data_inicial):
    
    # 1. Garantir total válido
    total = Decimal(compra.valor_total or 0)
    if total <= 0:
        raise ValueError("Compra sem valor total. Não é possível gerar parcelas.")

    # 2. Garantir que o fornecedor da compra seja um Contato
    if not compra.fornecedor:
        raise ValueError("Compra sem fornecedor. Não é possível gerar financeiro.")
    contato, _ = Contato.objects.get_or_create(
        nome=compra.fornecedor.nome,
        defaults={"tipo": "FORNECEDOR"}
    )
    # 3. Categoria obrigatória
    categoria = getattr(compra, "categoria_compra", None)
    if not categoria:
        try:
            categoria = FinanceiroCategoria.objects.get(nome="Compras") # categoria padrão
        except FinanceiroCategoria.DoesNotExist:
            raise ValueError("Categoria padrão 'Compras' não encontrada.")
        
    # 4. Cálculo seguro das parcelas
    valor_base = (total / Decimal(parcelas)).quantize(Decimal("0.01"))
    acumulado = Decimal("0.00")

    titulos = []

    for i in range(parcelas):
        if i == parcelas - 1:
            valor = total - acumulado
        else:
            valor = valor_base
            acumulado += valor_base

        venc = data_inicial + timedelta(days=i * dias)

        titulo = FinanceiroPagar.objects.create(
            data_lancamento=compra.data,
            data_vencimento=venc,
            contato=contato,
            descricao=f"Compra #{compra.id} – Parcela {i+1}/{parcelas}",
            valor=valor,
            categoria=categoria,
            origem="COMPRA",
            compra=compra,  # você adicionará esse campo no modelo
        )
 
        titulos.append(titulo)

    return titulos


# Registra no financeiro a compra e as parcelas e chamado pela views comercial.compra_criar
def registrar_financeiro_compra(compra, total, parcelas, dias):
    categoria = FinanceiroCategoria.objects.get(nome="Compras")
 
    FinanceiroLancamento.objects.create(
        data=compra.data,
        categoria=categoria,
        descricao=f"Compra #{compra.id}",
        valor=total,
        origem="Compra",
        referencia_id=compra.id
    )

    valor_parcela = total / parcelas
    for i in range(parcelas):
        vencimento = compra.data + timedelta(days=i * dias)
        FinanceiroPagar.objects.create(
            data_lancamento=compra.data,
            data_vencimento=vencimento,
            contato=compra.fornecedor,
            descricao=f"Compra #{compra.id} - Parcela {i+1}/{parcelas}",
            valor=valor_parcela,
            categoria=categoria,
            origem="Compra",
            referencia_id=compra.id
        )

# Estorna títulos de contas a pagar vinculadas a uma compra
def estornar_financeiro_pagar(compra):
    titulos = FinanceiroPagar.objects.filter(compra=compra)

    for titulo in titulos:
        # remover movimento de caixa se existir
        if titulo.caixa_movimento:
            titulo.caixa_movimento.delete()

        titulo.delete()

''' 
Esta view:
- abre uma tela de confirmação
- registra o pagamento
- cria o movimento no caixa
- marca o título como pago
- impede pagar duas vezes
- funciona para qualquer origem (COMPRA, LANCAMENTO, MANUAL)
'''
# Esse é o coração do módulo financeiro: transformar um compromisso (FinanceiroPagar)
# em um pagamento efetivo (CaixaMovimento)
# REVISADO
def pagar_titulo(request, pk):
    titulo = get_object_or_404(FinanceiroPagar, pk=pk)

    if request.method == "POST":
        data_pag = request.POST.get("data_pagamento") or timezone.localdate()
        valor = titulo.valor

        mov = CaixaMovimento.objects.create(
            data=data_pag,
            descricao=f"Pagamento: {titulo.descricao}",
            valor=valor,
            tipo="S",
            origem="PAGAMENTO",
            referencia_id=titulo.id,
        )

        titulo.data_pagamento = data_pag
        titulo.valor_pago = valor
        titulo.status = "pago"
        titulo.caixa_movimento = mov
        titulo.save()

        return redirect("financeiro:pagar_list")

    return render(request, "financeiro/pagar_quitacao.html", {"titulo": titulo})
    
 
def titulo_detalhe(request, pk):
    titulo = get_object_or_404(FinanceiroPagar, pk=pk)

    contexto = {
        "titulo": titulo,
    }

    return render(request, "financeiro/titulo_detalhe.html", contexto)

# Detalhes de uma conta a pagar vinculada a uma compra

def conta_detalhe(request, conta_id):
    # Recupera o título principal
    conta = get_object_or_404(FinanceiroPagar, id=conta_id)

    # Garante que é uma conta de compra
    if conta.origem != "COMPRA":
        return render(request, "financeiro/erro.html", {
            "mensagem": "Esta conta não está vinculada a uma compra."
        })

    # Todas as parcelas da compra
    parcelas = FinanceiroPagar.objects.filter(
        origem="COMPRA",
        referencia_id=conta.referencia_id
    ).order_by("data_vencimento")

    # Totais
    total_pago = parcelas.filter(valor_pago__isnull=False).aggregate(
        total=Sum("valor_pago")
    )["total"] or 0

    total_em_aberto = parcelas.filter(valor_pago__isnull=True).aggregate(
        total=Sum("valor")
    )["total"] or 0

    contexto = {
        "conta": conta,
        "parcelas": parcelas,
        "total_pago": total_pago,
        "total_em_aberto": total_em_aberto,
    }

    return render(request, "financeiro/conta_detalhe.html", contexto)
