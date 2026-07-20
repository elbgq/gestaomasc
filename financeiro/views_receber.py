
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from .models import FinanceiroReceber, CaixaMovimento
from comercial.models import Venda
from django.utils import timezone
from django.core.paginator import Paginator
from .forms import FinanceiroReceberForm
from django.shortcuts import render, get_object_or_404, redirect
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from django.contrib import messages

# Lista de títulos a receber - REVISADO
class ReceberListView(ListView):
    model = FinanceiroReceber
    template_name = "financeiro/receber_list.html"
    context_object_name = "titulos"
    paginate_by = None # Desativa paginação automática do ListView

    def get_queryset(self):
        return (
            FinanceiroReceber.objects
            .exclude(status="cancelado")
            .order_by("data_vencimento")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        context["hoje"] = hoje

        titulos = context["titulos"]

        # -----------------------------
        # SEPARAÇÃO ENTRE ABAS
        # -----------------------------
        receitas_vendas = titulos.filter(origem__in=["VENDA"])
        receitas_avulsas = titulos.exclude(origem__in=["VENDA"])
 
        # -----------------------------
        # PAGINAÇÃO INDEPENDENTE
        # -----------------------------
        page_vendas = self.request.GET.get("page_vendas")
        page_avulsas = self.request.GET.get("page_avulsas")

        paginator_vendas = Paginator(receitas_vendas, 20)
        paginator_avulsas = Paginator(receitas_avulsas, 20)

        page_obj_vendas = paginator_vendas.get_page(page_vendas)
        page_obj_avulsas = paginator_avulsas.get_page(page_avulsas)

        # -----------------------------
        # CONTEXTO FINAL
        # -----------------------------
        context.update({
            "page_obj_vendas": page_obj_vendas,
            "paginator_vendas": paginator_vendas,

            "page_obj_avulsas": page_obj_avulsas,
            "paginator_avulsas": paginator_avulsas,

            # Para manter filtros nos links do paginator
            "params": self.request.GET.urlencode(),
        })

        return context
# ======================

 
# Criar novo título a receber
class ReceberCreateView(CreateView):
    model = FinanceiroReceber
    form_class = FinanceiroReceberForm
    
    template_name = "financeiro/receber_form.html"
    success_url = reverse_lazy("financeiro:receber_list")

    def form_valid(self, form):
        titulo = form.save(commit=False)
        titulo.valor_pago = Decimal("0.00")
        titulo.status = "pendente"
        titulo.origem = "MANUAL"
        titulo.save()
        return super().form_valid(form)

# Atualizar título a receber - REVISADO
class ReceberUpdateView(UpdateView):
    model = FinanceiroReceber
    form_class = FinanceiroReceberForm
    template_name = "financeiro/receber_form.html"
    success_url = reverse_lazy("financeiro:receber_list")


class ReceberDeleteView(DeleteView):
    model = FinanceiroReceber
    template_name = "financeiro/receber_confirm_delete.html"
    success_url = reverse_lazy("financeiro:receber_list")
    
    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.origem != "Manual":
            messages.error(request, "Este título só pode ser excluído na sua origem.")
            return redirect("financeiro:receber_list")
        return super().delete(request, *args, **kwargs)

# Receber título - REVISADO
 
def receber_titulo(request, pk):
    titulo = get_object_or_404(FinanceiroReceber, pk=pk)

    if request.method == "POST":
        data_pag = request.POST.get("data_pagamento") or timezone.localdate()
        valor = titulo.valor

        # Criar movimento de caixa
        mov = CaixaMovimento.objects.create(
            data=data_pag,
            descricao=f"Recebimento: {titulo.descricao}",
            valor=valor,
            tipo="E",
            origem="RECEITA",
            content_type=ContentType.objects.get_for_model(titulo),
            object_id=titulo.id,
        )

        # Atualizar título
        titulo.caixa_movimento = mov
        titulo.data_pagamento = data_pag
        titulo.valor_pago = valor
        titulo.status = "pago"
        titulo.save()

        return redirect("financeiro:receber_list")

    return render(request, "financeiro/receber_quitacao.html", {"titulo": titulo})
