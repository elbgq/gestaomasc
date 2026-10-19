# Import para views genéricas do Django para compras, vendas e estoque
from comercial.models import (
        Estoque, Venda, MovimentacaoEstoque
)
from comercial.forms import (
    VendaForm, VendaItemFormSet,
    ParcelamentoForm,
    )

# Adicional imports para views de dashboard e relatórios
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import F, Sum
# Adiconal imports para views de formulário de upload de faturas
from django.contrib import messages
from datetime import timedelta, date
from decimal import Decimal, ROUND_HALF_UP
from comercial.models import (
    MovimentacaoEstoque, Estoque, Venda, CMVItem
)
from cadastros.models import Produto, Servico
from comercial.forms import FiltroDashboardForm
# Integração das vendas com o financeiro
from financeiro.models import (
    FinanceiroCategoria, FinanceiroReceber, CaixaMovimento
)
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from comercial.views.views_estoque import registrar_cmv, estornar_saidas_venda


# Títulos a receber gerados para a venda
def titulos_da_venda(venda):
    return FinanceiroReceber.objects.filter(
        origem="VENDA",
        content_type=ContentType.objects.get_for_model(Venda),
        object_id=venda.id,
    )

#=========================================
# VIEWS PARA VENDAS DE PRODUTOS E SERVIÇOS
#=========================================
# Criação de vendas genérica (produtos e serviços) "REVISADA"
def venda_create(request):

    if request.method == "POST":
        form = VendaForm(request.POST)
        itens_formset = VendaItemFormSet(request.POST, prefix="itens")

        if form.is_valid() and itens_formset.is_valid():
            venda = form.save(commit=False)
            venda.status = "rascunho"
            venda.save()

            itens_formset.instance = venda
            itens_formset.save()

            return redirect("comercial:venda_editar", venda.id)

        # Se chegou aqui → algum dos dois é inválido
        return render(request, "comercial/venda_form.html", {
            "form": form,
            "itens_formset": itens_formset,
            "excluir": ["numero", "total", "cmv", "data_finalizacao", "status", "forma_pagamento"],
            "total": 0,
            "venda": None,
            "produtos": Produto.objects.all(),
            "servicos": Servico.objects.all(),
        })

    # GET
    form = VendaForm(initial={
        "data_emissao": date.today().strftime("%Y-%m-%d")
    })
    itens_formset = VendaItemFormSet(prefix="itens")

    return render(request, "comercial/venda_form.html", {
        "form": form,
        "itens_formset": itens_formset,
        "excluir": ["numero", "total", "cmv", "data_finalizacao", "status", "forma_pagamento"],
        "total": 0,
        "venda": None,
        "produtos": Produto.objects.all(),
        "servicos": Servico.objects.all(),
    })
    
    

# Edição de vendas "REVISADA"
def venda_editar(request, venda_id):
    venda = get_object_or_404(Venda, id=venda_id)
    
    # 1. Impede edição se houver títulos recebidos
    if titulos_da_venda(venda).filter(valor_pago__gt=0).exists():
        messages.error(request, "Esta venda possui parcelas já recebidas e não pode ser editada.")
        return redirect("comercial:venda_detalhe", venda.id)
    
    # Campos removidos do form principal
    excluir = ["numero", "total", "cmv", "data_finalizacao", "status", "forma_pagamento"]

    # Produtos e serviços para os selects
    produtos = Produto.objects.all()
    servicos = Servico.objects.all()

    # Detecta se o fluxo deve continuar para parcelamento
    continuar_fluxo = (
        request.GET.get("continuar") == "1" or
        request.POST.get("continuar") == "1"
    )

    if request.method == "POST":
        form = VendaForm(request.POST, instance=venda)
        formset = VendaItemFormSet(request.POST, instance=venda, prefix="itens")

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()

                # Processa itens (custo médio, validações, etc.)
                processar_itens_venda(venda, formset)

                # Remove itens deletados
                for obj in formset.deleted_objects:
                    obj.delete()

                # 5. Atualiza total
                venda.atualizar_total()

                # Parcelada → vai para tela de parcelamento
                if continuar_fluxo:
                    return redirect("comercial:venda_parcelamento", venda.id)

                # À vista → finaliza e registra financeiro
                registrar_financeiro_venda(
                    venda,
                    parcelas=1,
                    dias=0,
                    data_inicial=date.today()
                )
                # Registra o CMV (estorna a baixa anterior se a venda já estava finalizada)
                registrar_cmv(venda)

                if venda.forma_pagamento in (None, "", "parcelado"):
                    venda.forma_pagamento = "avista"
                venda.status = "finalizada"
                venda.data_finalizacao = venda.data_finalizacao or timezone.now()
                venda.save()

            return redirect("comercial:venda_detalhe", venda.id)

    else:
        initial = {}
        if venda.data_emissao:
            initial["data_emissao"] = venda.data_emissao.strftime("%Y-%m-%d")

        form = VendaForm(instance=venda, initial=initial)
        formset = VendaItemFormSet(instance=venda, prefix="itens")

    return render(request, "comercial/venda_form.html", {
        "form": form,
        "itens_formset": formset,
        "venda": venda,
        "continuar_fluxo": continuar_fluxo,
        "total": venda.total,
        "excluir": excluir,
        "produtos": produtos,
        "servicos": servicos,
    })

 
# Lista de vendas "REVISADA"
def venda_list(request):
    vendas = Venda.objects.select_related('cliente').order_by("-data_emissao", "-numero")
    # Paginação manual
    paginator = Paginator(vendas, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    return render(
        request, "comercial/venda_list.html", {
            "vendas": vendas,
            "page_obj": page_obj
            })

# Detalhes da venda "REVISADA"
def venda_detalhe(request, venda_id):
    venda = get_object_or_404(Venda, id=venda_id)
    itens = (venda.itens.select_related('produto', 'servico').all())
    
    # Movimentos de caixa relacionados à venda à vista
    # Parcelas geradas(caso seja parcelada)
    parcelas = titulos_da_venda(venda).order_by("data_vencimento")

    # Recebimentos das parcelas no caixa
    movimento_caixa = CaixaMovimento.objects.filter(
        origem="RECEITA",
        referencia_tipo="R",
        referencia_id__in=list(parcelas.values_list("id", flat=True))
    ).order_by("data")

    return render(request, "comercial/venda_detalhe.html", {
        "venda": venda,
        "itens": itens,
        "movimento_caixa": movimento_caixa, # Usando a opção A
        "cmv_total": venda.cmv,
        "parcelas": parcelas,
        
    })


# Função de excluir rascunho de venda "REVISADA"
def venda_excluir(request, venda_id):
    venda = get_object_or_404(Venda, id=venda_id)

    # 1. Impede exclusão de vendas já finalizadas
    if venda.status == "finalizada":
        messages.error(request, "Vendas finalizadas não podem ser excluídas.")
        return redirect("comercial:venda_detalhe", venda.id)
    
    # 2. Impede exclusão se houver qualquer título financeiro gerado
    if titulos_da_venda(venda).exists():

        messages.error(request, "Esta venda possui registros financeiros e não pode ser excluída.")
        return redirect("comercial:venda_detalhe", venda.id)
    
    # 3. Impede exclusão se houver movimentos de caixa associados
    if CaixaMovimento.objects.filter(
        origem="RECEITA",
        referencia_id=venda.id
    ).exists():
        messages.error(request, "Esta venda possui movimentação de caixa e não pode ser excluída.")
        return redirect("comercial:venda_detalhe", venda.id)

    # 4. Exclusão confirmada
    if request.method == "POST":
        venda.delete()
        return redirect("comercial:venda_list")
    return render(request, "comercial/venda_confirm_delete.html", {"venda": venda})

# Função auxiliar para processar itens de venda "REVISADA"
"""
    Processa itens da venda, tratando:
    - custo médio
    - validação produto/serviço
    - movimentações de estoque (se finalizada)
    - CMV
    - total da venda
"""
def processar_itens_venda(venda, formset):
    # A baixa de estoque e o CMV ficam em registrar_cmv, chamada na finalização
    itens = formset.save(commit=False)

    for item in itens:
        # Linha sem produto nem serviço é ignorada
        if not item.produto and not item.servico:
            continue

        # Congela custo médio apenas para produtos
        if item.produto:
            estoque = Estoque.objects.get(produto=item.produto)
            item.custo_medio = estoque.preco_medio

        # Atribui a venda ao item
        item.venda = venda
        item.save()

    # Recalcular total da venda
    venda.total = sum(i.total for i in venda.itens.all())
    venda.save()
    

# Função auxiliar par registrar financeiro da venda "REVISADA"
def registrar_financeiro_venda(venda, parcelas, dias, data_inicial):
    # Categoria padrão para receita de vendas
    categoria_receita, _ = FinanceiroCategoria.objects.get_or_create(
        nome="Receita de Vendas",
        defaults={"tipo": "R"}
    )
    ct = ContentType.objects.get_for_model(Venda)

    # 1. Apaga títulos pendentes antigos NÃO PAGOS
    FinanceiroReceber.objects.filter(
        origem="VENDA",        
        content_type=ct,
        object_id=venda.id,
        valor_pago=0
    ).delete()
    
    total = venda.total
    entrada = getattr(venda, "entrada", Decimal("0.00"))

    # 2. Se houver entrada (sinal)

    if entrada > 0:
        # Título pago na entrada
        FinanceiroReceber.objects.create(
            data_lancamento=date.today(),
            data_vencimento=date.today(),
            data_pagamento=date.today(),
            cliente=venda.cliente,
            descricao=f"Venda #{venda.id} - Entrada",
            valor=entrada,
            valor_pago=entrada,
            categoria=categoria_receita,
            origem="VENDA",
            content_type=ct,
            object_id=venda.id
        )
        
        # Registra entrada no caixa
        CaixaMovimento.objects.create(
            data=date.today(),
            descricao=f"Entrada da venda #{venda.id}",
            tipo="E",  # Entrada
            valor=entrada,
            origem="VENDA",  # ou "VENDA", se quiser adicionar essa origem
            referencia_id=venda.id
        )

        total -= entrada
    
    # 3. Vendas à vista (parcelas=1)
    if parcelas == 1:

        FinanceiroReceber.objects.create(
            data_lancamento=date.today(),
            data_vencimento=date.today(),
            data_pagamento=date.today(),
            cliente=venda.cliente,
            descricao=f"Venda #{venda.id} - À vista",
            valor=total,
            valor_pago=0, # Não quitar aki
            categoria=categoria_receita,
            origem="VENDA",
            content_type=ct,
            object_id=venda.id
        )

        return  # fim do fluxo para vendas à vista

    # ============================================================
    # 4. VENDA PARCELADA
    # ============================================================

    # Valor base da parcela
    valor_parcela = (total / parcelas).quantize( Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Ajuste da última parcela (para evitar centavos perdidos)
    ajuste = total - (valor_parcela * parcelas)

    for i in range(parcelas):
        vencimento = data_inicial + timedelta(days=i * dias)
        # última parcela recebe ajuste
        valor = valor_parcela + (ajuste if i == parcelas - 1 else Decimal("0.00"))

        FinanceiroReceber.objects.create (
            data_lancamento=date.today(),
            data_vencimento=vencimento,
            cliente=venda.cliente,
            descricao=f"Venda #{venda.id} - Parcela {i+1}/{parcelas}",
            valor=valor,
            categoria=categoria_receita,
            origem="VENDA",
            content_type=ct,
            object_id=venda.id
        )



# Venda parcelamento "REVISADA"
def venda_parcelamento(request, venda_id):
    venda = get_object_or_404(Venda, id=venda_id)

    # Venda finalizada só pode ser parcelada de novo se nada foi recebido
    if titulos_da_venda(venda).filter(valor_pago__gt=0).exists():
        messages.error(request, "Esta venda possui parcelas já recebidas e não pode ser alterada.")
        return redirect("comercial:venda_detalhe", venda.id)

    if request.method == "POST":
        form = ParcelamentoForm(request.POST)
        
        if form.is_valid():
            parcelas = form.cleaned_data["parcelas"]
            dias = form.cleaned_data["dias_entre_parcelas"]
            data_inicial = form.cleaned_data["data_inicial"] or date.today()

            with transaction.atomic():
                # Registrar financeiro (parcelado)
                registrar_financeiro_venda(venda, parcelas, dias, data_inicial)

                # Registrar CMV (estorna a baixa anterior se a venda já estava finalizada)
                registrar_cmv(venda)

                # Definir a forma de pagamento como parcelado
                venda.forma_pagamento = "parcelado"
                venda.status = "finalizada"
                venda.data_finalizacao = venda.data_finalizacao or timezone.now()
                venda.save()

            return redirect("comercial:venda_detalhe", venda.id)
    else:
        form = ParcelamentoForm()

    return render(request, "comercial/venda_parcelamento.html", {
        "venda": venda,
        "form": form,
        "total": venda.total,
    })

# Views para o estorno de venda
def estornar_venda(venda):
    with transaction.atomic():

        # 1. Impedir estorno de venda com parcelas recebidas
        if titulos_da_venda(venda).filter(valor_pago__gt=0).exists():
            raise ValueError("Não é possível estornar venda com parcelas já recebidas.")

        # 2 a 4. Devolver ao estoque as saídas desta venda e apagar o CMV
        estornar_saidas_venda(venda)
        CMVItem.objects.filter(venda=venda).delete()
        venda.cmv = 0

        # 5. Estornar contas a receber (parcelas pendentes)
        titulos = titulos_da_venda(venda)

        # Nenhum título deve ter valor_pago > 0 (já validado acima)
        titulos.delete()

        # 6. Estornar caixa (se houve entrada à vista ou entrada/sinal)
        movimentos_caixa = CaixaMovimento.objects.filter(
            origem="VENDA",
            referencia_id=venda.id
        )

        for mov in movimentos_caixa:
            # Criar movimento inverso (SAÍDA)
            CaixaMovimento.objects.create(
                data=date.today(),
                descricao=f"Estorno da venda #{venda.id}",
                tipo="S",
                valor=mov.valor,
                origem="ESTORNO_VENDA",
                referencia_id=venda.id
            )

            mov.delete()

        # 7. Atualizar status da venda
        venda.status = "cancelada"
        venda.save()

        return True

# Recibo de venda
def venda_recibo(request, venda_id):
    venda = get_object_or_404(Venda, id=venda_id)
    itens = venda.itens.all()

    # Cálculo do CMV total (opcional, mas útil no recibo)
    cmv_total = sum(
        (item.custo_medio or 0) * item.quantidade
        for item in itens if item.produto
    )

    return render(request, "comercial/venda_recibo.html", {
        "venda": venda,
        "itens": itens,
        "cmv_total": cmv_total,
        "lucro": venda.total - cmv_total,
    })
 
# API endpoint para retornar preço do serviço


def api_preco(request, tipo, pk):

    # PRODUTO → preço + estoque
    if tipo == "produto":
        produto = Produto.objects.filter(id=pk).first()

        if not produto:
            return JsonResponse({"preco": 0, "estoque": 0})

        # Buscar estoque
        try:
            estoque = Estoque.objects.get(produto=produto)
            estoque_qtd = estoque.quantidade
        except Estoque.DoesNotExist:
            estoque_qtd = 0

        return JsonResponse({
            "preco": float(produto.preco_venda),
            "estoque": float(estoque_qtd),
        })

    # SERVIÇO → apenas preço
    if tipo == "servico":
        servico = Servico.objects.filter(id=pk).first()
        return JsonResponse({
            "preco": float(servico.preco_servico) if servico else 0,
            "estoque": None,  # serviços não têm estoque
        })

    # Tipo desconhecido
    return JsonResponse({"preco": 0, "estoque": None})


#==========================
# DASHBOARD
#==========================

# Dashboard comercial
def dashboard_comercial(request):
    form = FiltroDashboardForm(request.GET or None)
    estoque_qs = Estoque.objects.select_related("produto").all()

    if form.is_valid():
        data_inicio = form.cleaned_data.get("data_inicio")
        data_fim = form.cleaned_data.get("data_fim")
        produto = form.cleaned_data.get("produto")

        if produto:
            estoque_qs = estoque_qs.filter(produto=produto)

        if data_inicio and data_fim:
            estoque_qs = estoque_qs.filter(
                produto__movimentacaoestoque__data__range=(data_inicio, data_fim)
            )

    total_estoque = estoque_qs.aggregate(
        valor_total=Sum(F("quantidade") * F("preco_medio"))
    )["valor_total"] or 0

    return render(request, "comercial/dashboard.html", {
        "form": form,
        "total_estoque": total_estoque,
        "estoques": estoque_qs,
    })
