
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404
from django.contrib import messages
from django.views.generic import DetailView, TemplateView
from django.urls import reverse_lazy
from django.utils import timezone
from django.http import JsonResponse
from cadastros.models import Contato
from financeiro.models import FinanceiroCategoria, FinanceiroReceber, FinanceiroPagar
from financeiro.services import (
    FinanceiroErro, buscar_titulo, categoria_sugerida, estornar_quitacao, quitar_titulo,
    reclassificar_categoria, titulo_pago
)
from datetime import date
from decimal import Decimal, InvalidOperation
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
    
# Lê a data da quitação digitada; vazia ou inválida vira hoje
def ler_data(texto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return timezone.localdate()


# Campos da quitação: valor quitado (vazio = tudo), juros, multa e desconto
def ler_quitacao(post):
    def numero(nome):
        texto = (post.get(nome) or "").strip().replace(",", ".")
        if not texto:
            return None
        try:
            return Decimal(texto)
        except InvalidOperation:
            raise FinanceiroErro("Valor inválido na quitação.")
    return {
        "data": ler_data(post.get("data_pagamento")),
        "valor": numero("valor_quitado"),
        "juros": numero("valor_juros") or 0,
        "multa": numero("valor_multa") or 0,
        "desconto": numero("valor_desconto") or 0,
    }


def titulo_quitacao_view(request, tipo, pk):
    titulo = buscar_titulo(tipo, pk)
    if titulo is None:
        raise Http404("Título não encontrado")

    if titulo_pago(titulo):
        messages.warning(request, "Este título já foi quitado.")
        return redirect("financeiro:titulo_detalhe", titulo.tipo, titulo.id)

    # GET → mostra tela de confirmação
    if request.method != "POST":
        return render(request, "financeiro/titulo_confirmar_quitacao.html", {
            "titulo": titulo,
            "hoje": timezone.localdate(),
        })

    try:
        quitar_titulo(titulo, **ler_quitacao(request.POST))
    except FinanceiroErro as erro:
        messages.error(request, str(erro))
        return redirect("financeiro:titulo_confirmar_quitacao", titulo.tipo, titulo.id)
    else:
        messages.success(request, "Título quitado com sucesso!")
    return redirect("financeiro:titulo_detalhe", titulo.tipo, titulo.id)


# Desfaz uma quitação lançada errado
def titulo_estornar_quitacao(request, tipo, pk):
    titulo = buscar_titulo(tipo, pk)
    if titulo is None:
        raise Http404("Título não encontrado")

    if not titulo_pago(titulo):
        messages.warning(request, "Este título não está quitado.")
        return redirect("financeiro:titulo_detalhe", titulo.tipo, titulo.id)

    if request.method != "POST":
        return render(request, "financeiro/titulo_estornar_quitacao.html", {"titulo": titulo})

    try:
        estornar_quitacao(titulo)
    except FinanceiroErro as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Quitação estornada. O título voltou para em aberto.")
    return redirect("financeiro:titulo_detalhe", titulo.tipo, titulo.id)


# Troca a categoria de um título, inclusive já quitado (não mexe no caixa)
def titulo_reclassificar(request, tipo, pk):
    titulo = buscar_titulo(tipo, pk)
    if titulo is None:
        raise Http404("Título não encontrado")

    categorias = FinanceiroCategoria.objects.filter(tipo=titulo.tipo).order_by("nome")

    if request.method == "POST":
        categoria = categorias.filter(pk=request.POST.get("categoria")).first()
        if categoria is None:
            messages.error(request, "Escolha uma categoria.")
            return redirect("financeiro:titulo_reclassificar", titulo.tipo, titulo.id)
        try:
            reclassificar_categoria(titulo, categoria, request.user.get_username())
        except FinanceiroErro as erro:
            messages.error(request, str(erro))
            return redirect("financeiro:titulo_reclassificar", titulo.tipo, titulo.id)
        messages.success(request, f"Categoria alterada para {categoria.nome}.")
        return redirect("financeiro:titulo_detalhe", titulo.tipo, titulo.id)

    return render(request, "financeiro/titulo_reclassificar.html", {"titulo": titulo, "categorias": categorias})


# Categoria sugerida para o contato escolhido no formulário (usada pelo JavaScript)
def api_categoria_sugerida(request, contato_id):
    contato = get_object_or_404(Contato, pk=contato_id)
    tipo = request.GET.get("tipo") or None
    categoria, origem = categoria_sugerida(contato, tipo if tipo in ("D", "R") else None)
    return JsonResponse({
        "contato": contato.nome,
        "categoria_id": categoria.id if categoria else None,
        "categoria": categoria.nome if categoria else None,
        "origem": origem,
    })
