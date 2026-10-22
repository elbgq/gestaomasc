from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from .models import FinanceiroLancamento, FinanceiroPagar, FinanceiroReceber, FinanceiroCategoria
from .forms import LancamentoForm
from .services import titulo_pago
from django.contrib.contenttypes.models import ContentType

class LancamentoListView(ListView):
    model = FinanceiroLancamento
    template_name = "financeiro/lancamento_list.html"
    context_object_name = "lancamentos"
    paginate_by = None  # Desativa paginação automática do ListView

    def get_queryset(self):
        return (
            FinanceiroLancamento.objects
            .select_related("contato", "categoria")
            .order_by("-data")  # ou o critério que você usa
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        hoje = timezone.localdate()
        context["hoje"] = hoje

        lancamentos = context["lancamentos"]

        # -----------------------------
        # SEPARAÇÃO ENTRE ABAS
        # -----------------------------
        lancamentos_receitas = lancamentos.filter(categoria__tipo="R")
        lancamentos_despesas = lancamentos.filter(categoria__tipo="D")

        # -----------------------------
        # PAGINAÇÃO INDEPENDENTE
        # -----------------------------
        page_receitas = self.request.GET.get("page_receitas")
        page_despesas = self.request.GET.get("page_despesas")

        paginator_receitas = Paginator(lancamentos_receitas, 20)
        paginator_despesas = Paginator(lancamentos_despesas, 20)

        page_obj_receitas = paginator_receitas.get_page(page_receitas)
        page_obj_despesas = paginator_despesas.get_page(page_despesas)

        # -----------------------------
        # CONTEXTO FINAL
        # -----------------------------
        context.update({
            "page_obj_receitas": page_obj_receitas,
            "paginator_receitas": paginator_receitas,

            "page_obj_despesas": page_obj_despesas,
            "paginator_despesas": paginator_despesas,

            # Para preservar filtros e parâmetros no paginator
            "params": self.request.GET.urlencode(),
        })

        return context
 
# Títulos (a pagar e a receber) gerados por um lançamento
def titulos_do_lancamento(lanc):
    filtro = {
        "origem": "LANCAMENTO",
        "content_type": ContentType.objects.get_for_model(FinanceiroLancamento),
        "object_id": lanc.id,
    }
    return FinanceiroPagar.objects.filter(**filtro), FinanceiroReceber.objects.filter(**filtro)


def lancamento_tem_titulo_pago(lanc):
    return any(titulo_pago(t) for qs in titulos_do_lancamento(lanc) for t in qs)


# Cria ou atualiza o título do lançamento: despesa gera conta a pagar, receita gera conta a receber.
# Se a categoria trocou de tipo, o título do tipo antigo (ainda em aberto) é apagado.
def sincronizar_titulo(lanc):
    pagar, receber = titulos_do_lancamento(lanc)
    despesa = lanc.categoria.tipo == "D"

    (receber if despesa else pagar).delete()
    modelo, contato = (FinanceiroPagar, "contato") if despesa else (FinanceiroReceber, "cliente")

    titulo, created = modelo.objects.get_or_create(
        origem="LANCAMENTO",
        content_type=ContentType.objects.get_for_model(FinanceiroLancamento),
        object_id=lanc.id,
        defaults={
            "data_lancamento": lanc.data,
            "data_vencimento": lanc.data,
            "descricao": lanc.descricao,
            "valor": lanc.valor,
            "categoria": lanc.categoria,
            contato: lanc.contato,
        }
    )
    if not created:
        titulo.data_lancamento = lanc.data
        titulo.data_vencimento = lanc.data  # ou outra regra
        setattr(titulo, contato, lanc.contato)
        titulo.descricao = lanc.descricao
        titulo.valor = lanc.valor
        titulo.categoria = lanc.categoria
        titulo.save()
    return titulo


class LancamentoCreateView(CreateView):
    model = FinanceiroLancamento
    form_class = LancamentoForm
    template_name = "financeiro/lancamento_form.html"
    success_url = reverse_lazy("financeiro:lancamento_list")

    def form_valid(self, form):
        with transaction.atomic():
            lanc = form.save()
            sincronizar_titulo(lanc)
        return redirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]

        cat_id = form["categoria"].value()

        if cat_id:
            categoria = FinanceiroCategoria.objects.filter(id=cat_id).first()
        else:
            categoria = None

        context["categoria_selecionada"] = categoria
        return context

# Atualizar lançamento financeiro (bloqueado se o título já foi quitado)
class LancamentoUpdateView(UpdateView):
    model = FinanceiroLancamento
    form_class = LancamentoForm
    template_name = "financeiro/lancamento_form.html"
    success_url = reverse_lazy("financeiro:lancamento_list")

    def dispatch(self, request, *args, **kwargs):
        if lancamento_tem_titulo_pago(self.get_object()):
            messages.error(request, "O título deste lançamento já foi quitado. Estorne a quitação antes de alterar; "
                           "para trocar só a categoria, use Alterar Categoria no detalhe do título.")
            return redirect("financeiro:lancamento_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            lanc = form.save()
            sincronizar_titulo(lanc)
        return redirect(self.success_url)


# Excluir lançamento exclui o título dele (bloqueado se o título já foi quitado)
class LancamentoDeleteView(DeleteView):
    model = FinanceiroLancamento
    template_name = "financeiro/lancamento_confirm_delete.html"
    success_url = reverse_lazy("financeiro:lancamento_list")

    def dispatch(self, request, *args, **kwargs):
        if lancamento_tem_titulo_pago(self.get_object()):
            messages.error(request, "O título deste lançamento já foi quitado. Estorne a quitação antes de excluir.")
            return redirect("financeiro:lancamento_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            for qs in titulos_do_lancamento(self.object):
                qs.delete()
            self.object.delete()
        return redirect(self.success_url)
