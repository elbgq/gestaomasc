
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404
from django.contrib import messages
from django.views.generic import DetailView, TemplateView
from django.urls import reverse_lazy
from django.utils import timezone
from financeiro.models import FinanceiroReceber, FinanceiroPagar, CaixaMovimento, Caixa
from django.core.paginator import Paginator


class TituloListView(TemplateView):
    template_name = "financeiro/titulo_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        titulos_pagar = FinanceiroPagar.objects.all()
        titulos_receber = FinanceiroReceber.objects.all()

        # Paginação separada
        page_receber = self.request.GET.get("page_receber")
        page_pagar = self.request.GET.get("page_pagar")

        paginator_receber = Paginator(titulos_receber, 20)
        paginator_pagar = Paginator(titulos_pagar, 20)

        page_obj_receber = paginator_receber.get_page(page_receber)
        page_obj_pagar = paginator_pagar.get_page(page_pagar)

        context.update({
            "page_obj_receber": page_obj_receber,
            "page_obj_pagar": page_obj_pagar,
            "paginator_receber": paginator_receber,
            "paginator_pagar": paginator_pagar,
            "is_paginated_receber": page_obj_receber.has_other_pages(),
            "is_paginated_pagar": page_obj_pagar.has_other_pages(),
        })
        return context
    
 
class TituloDetailView(DetailView):
    template_name = "financeiro/titulo_detalhe.html"

    def get_object(self, queryset=None):
        tipo = self.kwargs["tipo"]
        pk = self.kwargs["pk"]

        if tipo == "D":
            obj = get_object_or_404(FinanceiroPagar, pk=pk)
        elif tipo == "R":
            obj = get_object_or_404(FinanceiroReceber, pk=pk)
        else:
            raise Http404("Tipo inválido")

        # Debug
        print("TIPO NA URL:", tipo)
        print("PK NA URL:", pk)
        print("VALOR_PAGO NO BANCO:", obj.valor_pago)
        print("STATUS NO BANCO:", obj.status)
        return obj
        
    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)
        context["titulo"] = context["object"]
        return context
        
        # Tenta buscar em pagar
        # titulo = FinanceiroPagar.objects.filter(pk=pk).first()
        # if titulo:
        #   return titulo

        # Tenta buscar em receber
        # titulo = FinanceiroReceber.objects.filter(pk=pk).first()
        # if titulo:
        #    return titulo

        # raise Http404("Título não encontrado")
    
def titulo_quitacao_view(request, tipo, pk):

    # Carrega o título correto
    if tipo == "D":
        titulo = get_object_or_404(FinanceiroPagar, pk=pk)
    elif tipo == "R":
        titulo = get_object_or_404(FinanceiroReceber, pk=pk)
    else:
        raise Http404("Tipo Inválido!")

    # Impede quitação duplicada
    if not titulo:
        raise Http404("Título não encontrado")

    if titulo.esta_pago():
        messages.warning(request, "Este título já foi quitado.")
        return redirect("financeiro:titulo_detalhe", titulo.tipo, titulo.id)
    
    # GET → mostra tela de confirmação
    if request.method != "POST":
        return render(
            request,
            "financeiro/titulo_confirmar_quitacao.html",
            {"titulo": titulo}
        )

    # POST → processa quitação
    
    caixa = Caixa.objects.get(nome="Caixa Principal")
    saldo = caixa.saldo_atual()

    # Verifica saldo para despesas
    if isinstance(titulo, FinanceiroPagar) and saldo < titulo.valor:
        messages.error(request, "Saldo insuficiente no caixa para quitar este título.")
        return redirect("financeiro:titulo_detalhe", titulo.tipo, titulo.id)

    # # Define tipo e origem do movimento
    if isinstance(titulo, FinanceiroPagar):
        tipo_mov = "S"  # Saída
        origem_mov = "PAGAMENTO"
    else:
        tipo_mov = "E"  # Entrada
        origem_mov = "RECEITA"

    # Marca título como quitado
    titulo.status = "pago"
    titulo.valor_pago = titulo.valor
    titulo.data_pagamento = timezone.now().date()
    titulo.save()
    
    # Cria movimento no caixa
    CaixaMovimento.objects.create(
        caixa=caixa,
        data=timezone.localdate(),
        descricao=f"{titulo.descricao} (Quitação de Título)",
        tipo=tipo_mov, 
        valor=titulo.valor,
        origem=origem_mov,  # ← AGORA SIM
        referencia_id=titulo.id,
    )

    messages.success(request, "Título quitado com sucesso!")
    return redirect("financeiro:titulo_detalhe", titulo.tipo, titulo.id)

