# Import para views genéricas do Django para compras, vendas e estoque
from comercial.models import (
        Estoque, Compra, CompraItem, MovimentacaoEstoque, ProdutoFornecedor
)
from comercial.forms import (
    ImportarCompraForm, CompraForm, CompraItemFormSet,
    ParcelamentoForm
)

# Adicional imports para views de dashboard e relatórios
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.utils import timezone 
from datetime import timedelta, date

# Adiconal imports para views de formulário de upload de faturas
import csv
from django.contrib import messages
from cadastros.models import Produto, Contato
from cadastros.precos import produtos_sinalizados
from django.core.paginator import Paginator
from django.db.models import Count, Q, F, Sum
from decimal import Decimal, ROUND_HALF_UP
from comercial.models import (
    Compra, CompraItem, MovimentacaoEstoque, Estoque
)

from comercial.services.xml_importer import XmlCompraImporter
from django.db import transaction, models
from django.contrib.contenttypes.models import ContentType

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

            # A finalização (estoque e financeiro) é feita em "Encerrar Compra"
            return redirect("comercial:compra_list")

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

    # Compra finalizada já movimentou estoque e financeiro
    if compra.confirmada:
        messages.error(request, "Compra já finalizada não pode ser editada.")
        return redirect("comercial:compra_detalhe", compra_id=compra.id)

    if request.method == "POST":
        acao = request.POST.get("acao")
        form = CompraForm(request.POST, instance=compra)
        itens_formset = CompraItemFormSet(request.POST, instance=compra)

        if form.is_valid() and itens_formset.is_valid():
            with transaction.atomic():
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

            if acao == "encerrar":
                return redirect("comercial:compras_confirmar", compra_id=compra.id)
            return redirect("comercial:compra_editar", compra_id=compra.id)


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

    if not compra_pode_finalizar(request, compra):
        return redirect("comercial:compra_detalhe", compra.id)

    with transaction.atomic():
        # Criar FinanceiroPagar (a quitação é feita em Contas a Pagar)
        FinanceiroPagar.objects.create(
            data_lancamento=compra.data,
            data_vencimento=compra.data,
            contato=compra.fornecedor,
            descricao=f"Compra #{compra.id} – À vista",
            valor=compra.valor_total,
            categoria=compra.categoria_financeira,
            origem="COMPRA",
            compra=compra,
            referencia=compra,
        )

        # Atualizar estoque
        resumo = registrar_compra(compra)

        # Finalizar compra
        compra.marcar_confirmada()

    avisar_precos(request, resumo)
    return redirect("comercial:compra_detalhe", compra.id)

# Criação de ContarPagar e ParcelaCompra na finalização parcelado
def compra_finalizar_parcelada(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    
    if request.method != "POST":
        return redirect("comercial:compras_confirmar", compra_id=compra.id)

    if not compra_pode_finalizar(request, compra):
        return redirect("comercial:compra_detalhe", compra.id)

    form = ParcelamentoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Dados de parcelamento inválidos.")
        return redirect("comercial:compras_confirmar", compra_id=compra.id)
    
    parcelas = form.cleaned_data["parcelas"]
    dias = form.cleaned_data["dias_entre_parcelas"]
    data_inicial = form.cleaned_data["data_inicial"] or date.today()

    valor_parcela = (compra.valor_total / parcelas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Última parcela recebe a diferença de arredondamento
    ajuste = compra.valor_total - (valor_parcela * parcelas)

    with transaction.atomic():
        for i in range(parcelas):
            vencimento = data_inicial + timedelta(days=i * dias)
            FinanceiroPagar.objects.create(
                data_lancamento=compra.data,
                data_vencimento=vencimento,
                contato=compra.fornecedor,
                descricao=f"Compra #{compra.id} – Parcela {i+1}/{parcelas}",
                valor=valor_parcela + (ajuste if i == parcelas - 1 else Decimal("0.00")),
                categoria=compra.categoria_financeira,
                origem="COMPRA",
                compra=compra,
                referencia=compra,
            )

        # Atualizar estoque
        resumo = registrar_compra(compra)

        # Finalizar compra
        compra.marcar_confirmada()

    avisar_precos(request, resumo)
    return redirect("comercial:compra_detalhe", compra.id)


# Download do XML da NF-e guardado na importação (para o contador e a guarda de 5 anos)
def compra_xml(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)
    if not compra.xml_nfe:
        messages.error(request, "Esta compra não tem XML de NF-e guardado.")
        return redirect("comercial:compra_detalhe", compra.id)
    nome = f"{compra.chave_acesso or compra.numero_nota}-nfe.xml"
    resposta = HttpResponse(compra.xml_nfe, content_type="application/xml; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


# Finalização usando as duplicatas (vencimentos e valores) que vieram na NF-e
def compra_finalizar_duplicatas(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)

    if request.method != "POST":
        return redirect("comercial:compras_confirmar", compra_id=compra.id)

    if not compra_pode_finalizar(request, compra):
        return redirect("comercial:compra_detalhe", compra.id)

    if not compra.duplicatas_conferem:
        messages.error(request, "As duplicatas da nota não somam o total da compra. Use o parcelamento manual.")
        return redirect("comercial:compras_confirmar", compra_id=compra.id)

    duplicatas = list(compra.duplicatas.all())
    with transaction.atomic():
        for i, dup in enumerate(duplicatas, 1):
            numero = f" ({dup.numero})" if dup.numero else ""
            FinanceiroPagar.objects.create(
                data_lancamento=compra.data,
                data_vencimento=dup.vencimento,
                contato=compra.fornecedor,
                descricao=f"Compra #{compra.id} – Parcela {i}/{len(duplicatas)}{numero}",
                valor=dup.valor,
                categoria=compra.categoria_financeira,
                origem="COMPRA",
                compra=compra,
                referencia=compra,
            )

        resumo = registrar_compra(compra)
        compra.marcar_confirmada()

    avisar_precos(request, resumo)
    return redirect("comercial:compra_detalhe", compra.id)


# Impede finalizar duas vezes ou com itens ainda não vinculados
def compra_pode_finalizar(request, compra):
    if compra.confirmada:
        messages.error(request, "Esta compra já foi finalizada.")
        return False
    if compra.tem_itens_pendentes:
        messages.error(request, "Existem itens pendentes. Vincule todos antes de finalizar.")
        return False
    return True
    

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
        Q(origem="COMPRA", referencia_id=compra.id) |
        # Entradas antigas eram gravadas com o id do item da compra
        Q(origem="Compra", referencia_id__in=list(itens.values_list("id", flat=True)))
    )

    titulos = FinanceiroPagar.objects.filter(
        Q(compra=compra) |
        Q(content_type=ContentType.objects.get_for_model(Compra), object_id=compra.id)
    ).distinct()
    
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
            "itens": itens,
            "duplicatas": compra.duplicatas.all(),
            "duplicatas_conferem": compra.duplicatas_conferem,
        })

    # POST → processa a finalização
    forma = request.POST.get("forma_pagamento")

    if forma == "avista":
        return compra_finalizar_avista(request, compra.id)

    elif forma == "parcelado":
        return compra_finalizar_parcelada(request, compra.id)

    elif forma == "duplicatas":
        return compra_finalizar_duplicatas(request, compra.id)

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
            quantidade=item.quantidade_estoque,
            preco=item.custo_unitario_estoque.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
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
                messages.error(request, " ".join(e.messages))
                return redirect("comercial:compras_importar")
            except Exception as e:
                messages.error(request, f"Erro inesperado ao processar o XML: {e}")
                return redirect("comercial:compras_importar")

            for aviso in importer.avisos:
                messages.warning(request, aviso)
            if compra.tem_itens_pendentes:
                messages.info(request, "Nota importada. Vincule os itens pendentes aos produtos do cadastro.")
            else:
                messages.success(request, "Nota importada e todos os itens foram vinculados automaticamente. Confira antes de confirmar.")
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

    if compra.confirmada:
        messages.error(request, "Esta compra já foi finalizada e os vínculos não podem mais ser alterados.")
        return redirect("comercial:compra_detalhe", compra.id)

    # 🔎 Ordenação: pendentes → vinculados → novos_produtos
    itens = compra.itens.select_related("produto").order_by(
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
        erros = []
        with transaction.atomic():
            for item in itens:
                escolha = request.POST.get(f"produto_{item.id}", "")
                fator = ler_fator(request.POST.get(f"fator_{item.id}"))
                if fator is None:
                    erros.append(f"Fator de conversão inválido em \"{item.descricao}\".")
                    continue
                item.fator_conversao = fator

                if escolha == "novo":
                    item.produto = criar_produto_do_item(item)
                    item.status = "novo_produto"
                elif escolha:
                    produto = Produto.objects.filter(id=escolha).first()
                    if produto:
                        item.produto = produto
                        item.status = "vinculado"
                else:
                    item.produto = None
                    item.status = "pendente"

                item.save()
                gravar_vinculo_fornecedor(compra.fornecedor, item)

        for erro in erros:
            messages.error(request, erro)
        if erros:
            return redirect("comercial:vincular_itens", compra_id=compra.id)

        if compra.tem_itens_pendentes:
            messages.warning(request, "Vinculações salvas. Ainda há itens pendentes.")
            return redirect("comercial:vincular_itens", compra_id=compra.id)

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


def ler_fator(valor):
    if valor in (None, ""):
        return Decimal("1")
    try:
        fator = Decimal(str(valor).replace(",", "."))
    except Exception:
        return None
    return fator if fator > 0 else None


# Cria o produto a partir dos dados do item da nota, usando o código do fornecedor como código de origem.
# Se a nota vem em embalagem com conversão (ex.: CX com 50), o produto é cadastrado em UN.
def criar_produto_do_item(item):
    unidade = item.unidade if item.fator_conversao == 1 else "UN"
    produto, _ = Produto.objects.get_or_create(
        codor=item.codigo_fornecedor[:10],
        descricao=item.descricao_importada[:255],
        defaults={
            "unidade": unidade,
            "ean": item.ean if item.fator_conversao == 1 else "",
            "ncm": item.ncm,
            "cest": item.cest,
        },
    )
    return produto


# Guarda o vínculo para que a próxima nota deste fornecedor já venha vinculada.
def gravar_vinculo_fornecedor(fornecedor, item):
    if not item.produto or not item.codigo_fornecedor:
        return
    ProdutoFornecedor.objects.update_or_create(
        fornecedor=fornecedor,
        codigo_fornecedor=item.codigo_fornecedor,
        defaults={
            "produto": item.produto,
            "ean": item.ean,
            "unidade_fornecedor": item.unidade_fornecedor,
            "fator_conversao": item.fator_conversao,
        },
    )


# Lança a entrada de cada item no estoque.
# O saldo e o preço médio são atualizados por MovimentacaoEstoque.save(), que também
# recalcula o preço de venda dos produtos automáticos. Devolve o resumo desses preços.
def registrar_compra(compra):
    precos_antes = {}
    for item in compra.itens.all():

        if not item.produto:
            continue

        precos_antes.setdefault(item.produto_id, item.produto.preco_venda)
        MovimentacaoEstoque.objects.create(
            produto=item.produto,
            tipo="ENTRADA",
            quantidade=item.quantidade_estoque,
            preco=item.custo_unitario_estoque.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            origem="COMPRA",
            referencia_id=compra.id
        )

    return resumo_precos(precos_antes)


# Preços que a compra alterou e produtos que ficaram com o preço sinalizado
def resumo_precos(precos_antes):
    produtos = list(Produto.objects.filter(pk__in=precos_antes).order_by("descricao"))
    return {
        "atualizados": [
            (p, precos_antes[p.pk], p.preco_venda) for p in produtos if p.preco_venda != precos_antes[p.pk]
        ],
        "sinalizados": produtos_sinalizados(produtos),
    }


def _reais(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


# Mostra o resumo de preços depois de finalizar a compra
def avisar_precos(request, resumo):
    if resumo["atualizados"]:
        lista = "; ".join(f"{p.descricao}: {_reais(antes)} → {_reais(novo)}" for p, antes, novo in resumo["atualizados"])
        messages.info(request, f"Preço de venda atualizado pelo novo custo: {lista}.")
    if resumo["sinalizados"]:
        nomes = ", ".join(linha["produto"].descricao for linha in resumo["sinalizados"])
        messages.warning(request, f"Preço de venda para conferir em Revisão de preços: {nomes}.")
