# Import para views genéricas do Django para compras, vendas e estoque
from comercial.models import (
        Estoque, Compra, CompraItem, MovimentacaoEstoque
)
from comercial.forms import (
    ImportarCompraForm, CompraForm, CompraItemFormSet,
    ParcelamentoForm
)

# Adicional imports para views de dashboard e relatórios
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone 
from datetime import timedelta, date

# Adiconal imports para views de formulário de upload de faturas
import csv
from django.contrib import messages
from cadastros.models import Produto, Contato
from django.core.paginator import Paginator
from django.db.models import Count, Q, F, Sum
from decimal import Decimal, ROUND_HALF_UP
from comercial.models import (
    Compra, CompraItem, MovimentacaoEstoque, Estoque
)

from comercial.services.xml_importer import XmlCompraImporter
from django.db import transaction, models

# Integração das vendas com o financeiro
from financeiro.models import (
    FinanceiroCategoria, FinanceiroLancamento, FinanceiroPagar,
    CaixaMovimento
)

from financeiro.models import FinanceiroCategoria
from django.utils import timezone

from django.core.exceptions import ValidationError

#===========================================
# COMPRAS
#===========================================
# NOVO MODELO DE PROCESSAMENTO DE COMPRA
def criar_compra(request):
        
    if request.method == "POST":
        acao = request.POST.get("acao")
        forma_pagamento = request.POST.get("forma_pagamento")
        form = CompraForm(request.POST)
        itens_formset = CompraItemFormSet(request.POST)

        if form.is_valid() and itens_formset.is_valid():
            with transaction.atomic():
                compra = form.save()

                # Salva itens
                itens = itens_formset.save(commit=False)
                for item in itens:
                    item.compra = compra
                    item.total = item.quantidade * item.preco_unitario
                    item.save()

                # Exclui itens marcados para remoção
                #for item in itens_formset.deleted_objects:
                #    item.delete()

                # Atualiza valor total
                compra.atualizar_valor_total()
                
                # FINALIZAÇÃO DA COMPRA
                if acao == "finalizar":
                    
                    if forma_pagamento == "avista":
                        compra.confirmar(
                            forma_pagamento="avista"
                        )

                    elif forma_pagamento == "parcelado":
                        compra.confirmar(
                            forma_pagamento="parcelado",
                            num_parcelas=int(request.POST.get("num_parcelas")),
                            intervalo_parcelas=int(request.POST.get("intervalo_parcelas")),
                            primeiro_vencimento=request.POST.get("primeiro_vencimento")
                        )
                # Se marcada como confirmada → processa
                #if compra.confirmada:
                #    compra.confirmar()

            return redirect("comercial:compra_list", compra.id)

    else:
        form = CompraForm()
        itens_formset = CompraItemFormSet()

    return render(request, "comercial/compras_form.html", {
        "form": form,
        "itens_formset": itens_formset,
        "compra": None
    })

# NOVO MODELO DE EDIÇÃO DE COMPRA
def editar_compra(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    estava_confirmada = compra.confirmada

    if request.method == "POST":
        acao = request.POST.get("acao")
        forma_pagamento = request.POST.get("forma_pagamento")
        form = CompraForm(request.POST, instance=compra)
        itens_formset = CompraItemFormSet(request.POST, instance=compra)

        if form.is_valid() and itens_formset.is_valid():
            with transaction.atomic():

                # Se estava confirmada → estornar antes de alterar
                if estava_confirmada:
                    compra.estornar()

                compra = form.save()

                # Salva itens
                itens = itens_formset.save(commit=False)
                for item in itens:
                    item.compra = compra
                    item.total = item.quantidade * item.preco_unitario
                    item.save()

                # Remove itens excluídos
                for obj in itens_formset.deleted_objects:
                    obj.delete()

                # Atualiza valor total
                compra.atualizar_valor_total()
                
                # Se usuario
                if acao == "encerrar":
                    # Aqui você pode criar títulos financeiros
                    if forma_pagamento == "avista":
                        compra.confirmar(
                            forma_pagamento="avista"
                        )
                        # criar 1 título pago
                    elif forma_pagamento == "parcelado":
                        compra.confirmar(
                            forma_pagamento="parcelado",
                            num_parcelas = int(request.POST.get("num_parcelas") or 1),
                            intervalo_parcelas = int(request.POST.get("intervalo_parcelas") or 30),
                            primeiro_vencimento = request.POST.get("primeiro_vencimento") or compra.data
                            # criar parcelas aqui
                        )
            if acao == "encerrar":
                return redirect("comercial:compra_list")
            return redirect("comercial:compra_editar", compra_id=compra.id)
        else:
            print("ERROS FORM:", form.errors)
            print("ERROS FORMSET:", itens_formset.errors)
            print("POST:", request.POST)


    else:
        form = CompraForm(instance=compra)
        itens_formset = CompraItemFormSet(instance=compra)

    return render(request, "comercial/compras_form.html", {
        "form": form,
        "itens_formset": itens_formset,
        "compra": compra
    })
    
# Lista de compras
def compra_list(request):
    q = request.GET.get("q", "")

    queryset = (
        Compra.objects
        .annotate(
            itens_pendentes=Count(
                "itens",
                filter=Q(itens__status="pendente"),
            )
        )
        .order_by("-data", "id")
    )

    if q:
        queryset = queryset.filter(
            Q(numero_nota__icontains=q) |
            Q(fornecedor__nome__icontains=q)
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "comercial/compras_list.html",
        {
            "page_obj": page_obj,
            "compras": page_obj.object_list,
            "q": q,
            "request": request,
        }
    )
    
# Compras parceladas
def compra_parcelas(request, compra_id):

    compra = get_object_or_404(Compra, id=compra_id)

    parcelas = FinanceiroPagar.objects.filter(
        origem="Compra",
        referencia_id=compra.id
    ).order_by("data_vencimento")
 
    context = {
        "compra": compra,
        "parcelas": parcelas,
    }
 
    return render(request, "comercial/compras_parcelas.html", context)

# View para excluir uma compra
def compra_excluir(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)

    # Impedir exclusão de compra já finalizada
    if compra.confirmada:
        messages.error(request, "Não é possível excluir uma compra já finalizada.")
        return redirect("comercial:compra_detalhe", compra_id=compra.id)

    if request.method == "POST":
        # Estorna movimentações, estoque, etc.
        estornar_compra(compra)
        # Exclui a compra
        compra.delete()
        messages.success(request, "Compra excluída com sucesso.")
        return redirect("comercial:compra_list")

    return render(request, "comercial/compras_confirm_delete.html", {
        "compra": compra
    })

# Views para validar a compra, registrar saída no caixa, criar ContaPagar já quitada,
# criar ParcelaCompra paga, marcar a compra como finalizada e - redirecionar para o
# detalhe da compra
def compra_finalizar_avista(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)

    if request.method != "POST":
        return redirect("comercial:compras_confirmar", compra_id=compra.id)

    categoria, _ = FinanceiroCategoria.objects.get_or_create(
        nome="Compras",
        defaults={"tipo": "D"}
    )

    # Criar FinanceiroPagar já quitado
    FinanceiroPagar.objects.create(
        data_lancamento=compra.data,
        data_vencimento=compra.data,
        contato=compra.fornecedor,
        descricao=f"Compra #{compra.id} – À vista",
        valor=compra.valor_total,
        categoria=categoria,
        origem="COMPRA",
        referencia=compra,
    )
    
    # Atualizar estoque e marcar compra como finalizada
    registrar_compra(compra)

    # Finalizar compra
    compra.confirmada = True
    compra.save()

    return redirect("comercial:compra_detalhe", compra.id)

# Criação de ContarPagar e ParcelaCompra na finalização parcelado
def compra_finalizar_parcelada(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    
    if request.method != "POST":
        return redirect("comercial:compras_confirmar", compra_id=compra.id)

    form = ParcelamentoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Dados de parcelamento inválidos.")
        return redirect("comercial:compras_confirmar", compra_id=compra.id)
    
    parcelas = form.cleaned_data["parcelas"]
    dias = form.cleaned_data["dias_entre_parcelas"]
    data_inicial = form.cleaned_data["data_inicial"] or date.today()
    
    categoria, _ = FinanceiroCategoria.objects.get_or_create(
        nome="Compras",
        defaults={"tipo": "D"}
    )

    valor_parcela = (compra.valor_total / parcelas).quantize(Decimal("0.01"))

    for i in range(parcelas):
        vencimento = data_inicial + timedelta(days=i * dias)
        # gerar_financeiro_pagar_da_compra(compra, parcelas, dias, data_inicial)
        FinanceiroPagar.objects.create(
            data_lancamento=compra.data,
            data_vencimento=vencimento,
            contato=compra.fornecedor,
            descricao=f"Compra #{compra.id} – Parcela {i+1}/{parcelas}",
            valor=valor_parcela,
            categoria=categoria,
            origem="COMPRA",
            referencia=compra, # ForeignKey correto
        )

    # Atualizar estoque e marcar compra como finalizada
    registrar_compra(compra)
    
    # Finalizar compra
    compra.confirmada = True
    compra.save()

    return redirect("comercial:compra_detalhe", compra.id)
    

# Confirmação de compra
def compra_detalhe(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)

    itens = compra.itens.all()
    # Paginação manual para os itens relacionados à compra
    paginator = Paginator(itens, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Opcional: movimentações relacionadas a esta compra
    movimentacoes = MovimentacaoEstoque.objects.filter(
        origem="Compra",
        referencia_id=compra.id)

    titulos = FinanceiroPagar.objects.filter(compra=compra)
    
    return render(request, "comercial/compras_detalhe.html", {
        "compra": compra,
        "itens": itens,
        "movimentacoes": movimentacoes,
        "titulos": titulos,
        "page_obj": page_obj,
    })
#===================================================================
# Confirmação de compra e atualização de estoque.
# Esta view realiza várias operações críticas: Atualiza o estoque, calcula preços médios,
# registra movimentações e atualiza o status dos itens e da compra.
# ATT: SOMENTE ESTA VIEW DEVE ALTERAR O ESTOQUE!
#===================================================================

def confirmar_compra(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    itens = compra.itens.all()

    # Não permite confirmar se houver itens pendentes
    if itens.filter(status="pendente").exists():
        messages.error(request, "Existem itens pendentes. Vincule todos antes de confirmar.")
        return redirect("comercial:vincular_itens", compra_id=compra.id)

    # GET → mostrar modal
    if request.method == "GET":
        return render(request, "comercial/compras_confirmar.html", {
            "compra": compra,
            "itens": itens
        })

    # POST → processa a finalização
    forma = request.POST.get("forma_pagamento")

    if forma == "avista":
        return compra_finalizar_avista(request, compra.id)

    elif forma == "parcelado":
        form = ParcelamentoForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Dados de parcelamento inválidos.")
            return redirect("comercial:compras_confirmar", compra_id=compra.id)
        parcelas = form.cleaned_data["parcelas"]
        dias = form.cleaned_data["dias_entre_parcelas"]
        data_inicial = form.cleaned_data["data_inicial"] or date.today()
        return compra_finalizar_parcelada(
            request,
            compra.id,
            parcelas,
            dias,
            data_inicial
        )

    messages.error(request, "Forma de pagamento inválida.")
    return redirect("comercial:compras_confirmar", compra_id=compra.id)


# NOVO MODELO DE PROCESSAMENTO DE COMPRA
def processar_confirmacao_compra(compra):
    """
    Gera movimentações de estoque para todos os itens da compra.
    Deve ser chamado SOMENTE quando compra.confirmada == True.
    """

    # Evita duplicar movimentações
    movimentacoes_existentes = MovimentacaoEstoque.objects.filter(
        origem="COMPRA",
        referencia_id=compra.id
    )

    if movimentacoes_existentes.exists():
        return  # já processado

    for item in compra.itens.all():
        if not item.produto:
            continue  # itens não vinculados não geram estoque

        MovimentacaoEstoque.objects.create(
            produto=item.produto,
            tipo="ENTRADA",
            quantidade=item.quantidade,
            preco=item.preco_unitario,
            origem="COMPRA",
            referencia_id=compra.id
        )
        
# NOVO MODELO DE ESTORNO DE COMPRA
def estornar_movimentacoes_compra(compra):
    movimentacoes = MovimentacaoEstoque.objects.filter(
        origem="COMPRA",
        referencia_id=compra.id
    )

    for mov in movimentacoes:
        mov.estornar()
        mov.delete()
        
# Views para estorno de compra - ANTIGO MODELO
def estornar_compra(compra):
    with transaction.atomic():
        
        # 1. Impedir estorno de compra já paga
        conta = getattr(compra, "conta_pagar", None)
        if compra.confirmada and conta:
            if conta.parcelas.filter(pago=True).exists():
                raise ValueError("Não é possível estornar compra com parcelas pagas.")
        
        # 2. Buscar todas as movimentações desta compra
        movimentacoes = MovimentacaoEstoque.objects.filter(
            origem="COMPRA",
            referencia_id=compra.id
        )

        produtos_afetados = {mov.produto for mov in movimentacoes}

        # 3. Estornar cada movimentações de estoque
        for mov in movimentacoes:
            mov.estornar()  # reverte o estoque
            mov.delete() # remove a movimentação do histórico

        # 4. Recalcular preço médio dos produtos afetados
        for produto in produtos_afetados:
            try:
                estoque = Estoque.objects.get(produto=produto)
                estoque.recalcular_preco_medio()
            except Estoque.DoesNotExist:
                pass # estoque pode não existir mais

        # 5. Estornar conta a pagar e parcelas 
        conta = getattr(compra, "conta_pagar", None)
        if conta:
            conta.parcelas.all().delete() # excluir parcelas
            conta.delete() # excluir conta

        # 6. NÃO excluir itens nem a compra aqui
        #    A edição da compra vai sobrescrever os itens
        return True

#======================================   
# Views principal para importar compras
#======================================
def importar_compra(request):
    
    if request.method == "POST":
        print(">>> ENTROU NA VIEW IMPORTAR_COMPRA <<<")
        arquivo = request.FILES.get("arquivo")

        if not arquivo:
            messages.error(request, "Nenhum arquivo enviado.")
            return redirect("comercial:compras_importar")

        nome = arquivo.name.lower()

        # ============================
        # IMPORTAÇÃO XML
        # ============================
        if nome.endswith(".xml"):
            from comercial.services.xml_importer import XmlCompraImporter

            try:
                importer = XmlCompraImporter(arquivo)
                compra = importer.importar()
            except ValidationError as e:
                messages.error(request, str(e))
                return redirect("comercial:compras_importar")
            except Exception as e:
                messages.error(request, f"Erro inesperado ao processar o XML: {e}")
                return redirect("comercial:compras_importar")


            return redirect("comercial:vincular_itens", compra_id=compra.id)

        # ============================
        # IMPORTAÇÃO CSV
        # ============================
        elif nome.endswith(".csv"):
            return importar_compra_csv(request, arquivo)

        else:
            messages.error(request, "Formato inválido. Envie um arquivo CSV ou XML.")
            return redirect("comercial:compras_importar")

    return render(request, "comercial/compras_importar.html")

#=====================================    
# Views para importar compras via XML
#=====================================
def importar_compra_xml(request):
    if request.method == "POST":
        form = ImportarCompraForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = request.FILES["arquivo"]

            from comercial.services.xml_importer import XmlCompraImporter
            importer = XmlCompraImporter(arquivo)

            try:
                compra = importer.importar()
            except Exception as e:
                messages.error(request, f"Erro ao importar XML: {e}")
                return redirect("comercial:compras_importar")

            return redirect("comercial:vincular_itens", compra_id=compra.id)

    else:
        form = ImportarCompraForm()

    return render(request, "comercial/compras_importar.html", {"form": form})


#=====================================    
# Views para importar compras via CSV
#=====================================
# Esta view é Função auxiliar para csv (reutiliza logica anterior)

def importar_compra_csv(request, arquivo):
    decoded = arquivo.read().decode("utf-8").splitlines()
    reader = csv.reader(decoded, delimiter=";")

    compra = Compra.objects.create(
        fornecedor=Contato.objects.first(),
        data=timezone.localdate(),
        numero_nota="IMPORTADA",
        valor_total=0,
        importada=True
    )

    total_compra = Decimal("0.00")

    for linha in reader:
        if not linha or len(linha) < 3:
            continue

        if all(not campo.strip() for campo in linha):
            continue

        descricao = linha[0].strip()
        quantidade_str = linha[1].strip()
        preco_str = linha[2].strip()

        if quantidade_str.lower() in ["quantidade", "qtd", "qtde"]:
            continue
        if preco_str.lower() in ["preco", "preço", "valor"]:
            continue

        try:
            quantidade = Decimal(quantidade_str.replace(",", "."))
            preco = Decimal(preco_str.replace(",", "."))
        except:
            messages.error(request, f"Erro ao converter valores na linha: {linha}")
            compra.delete()
            return redirect("comercial:compras_importar")

        total = quantidade * preco
        total_compra += total

        CompraItem.objects.create(
            compra=compra,
            descricao_importada=descricao,
            quantidade=quantidade,
            preco_unitario=preco,
            total=total,
            status="pendente"
        )

    compra.valor_total = total_compra
    compra.save()

    return redirect("comercial:vincular_itens", compra_id=compra.id)

#==========================================================  
# View para vincular itens importados a produtos existentes
#==========================================================
def vincular_itens(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    
    # Impedir vinculação quando a compra não é importada
    if not compra.importada:
        messages.error(request, "Esta compra não foi importada e não requer vinculação.")
        return redirect("comercial:compra_editar", compra.id)

    # 🔎 Ordenação: pendentes → vinculados → novos_produtos
    itens = compra.itens.all().order_by(
        models.Case(
            models.When(status="pendente", then=0),
            models.When(status="vinculado", then=1),
            models.When(status="novo_produto", then=2),
            default=3,
            output_field=models.IntegerField(),
        ),
        "descricao_importada"
    )
        
    if request.method == "POST":
        for item in itens:
            produto_id = request.POST.get(f"produto_{item.id}")

            if produto_id:
                try:
                    produto = Produto.objects.get(id=produto_id)
                    item.produto = produto
                    item.status = "vinculado"
                except Produto.DoesNotExist:
                    # Produto inválido enviado — ignora
                    pass
            else:
                # Se o item nunca foi vinculado, mantém como pendente
                if not item.produto:
                    item.status = "pendente"

            item.save()

        messages.success(request, "Itens vinculados com sucesso!")
        return redirect("comercial:compras_confirmar", compra_id=compra.id)
    
    # Lista de produtos para dropdown
    produtos = Produto.objects.all().order_by("descricao")
    # Verifica se ainda existem itens pendentes
    tem_pendentes = itens.filter(status="pendente").exists()

    return render(request, "comercial/vincular_itens.html", {
        "compra": compra,
        "itens": itens,
        "produtos": produtos,
        "tem_pendentes": tem_pendentes,
    })


def registrar_compra(compra):

    categoria_compras, _ = FinanceiroCategoria.objects.get_or_create(
        nome="Compras",
        defaults={"tipo": "D"}
    )

    # 2. Processar itens
    for item in compra.itens.all():

        if not item.produto:
            continue

        estoque, _ = Estoque.objects.get_or_create(
            produto=item.produto,
            defaults={"quantidade": 0, "preco_medio": 0}
        )

        quantidade_atual = Decimal(estoque.quantidade)
        preco_medio_atual = Decimal(estoque.preco_medio)

        quantidade_compra = Decimal(item.quantidade)
        preco_compra = Decimal(item.preco_unitario)

        # cálculo do novo preço médio
        if quantidade_atual > 0:
            preco_medio_novo = (
                (quantidade_atual * preco_medio_atual) +
                (quantidade_compra * preco_compra)
            ) / (quantidade_atual + quantidade_compra)

            preco_medio_novo = preco_medio_novo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            preco_medio_novo = preco_compra

        # atualizar estoque
        estoque.quantidade = quantidade_atual + quantidade_compra
        estoque.preco_medio = preco_medio_novo
        estoque.save()

        # movimentação
        MovimentacaoEstoque.objects.create(
            produto=item.produto,
            tipo="ENTRADA",
            quantidade=item.quantidade,
            preco=item.preco_unitario,
            origem="Compra",
            referencia_id=item.id
        )

