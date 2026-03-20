from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from .models import FinanceiroLancamento, FinanceiroPagar, FinanceiroReceber, FinanceiroCategoria
from .forms import LancamentoForm
from django.contrib.contenttypes.models import ContentType

class LancamentoListView(ListView):
    model = FinanceiroLancamento
    template_name = "financeiro/lancamento_list.html"
    context_object_name = "lancamentos"
  

class LancamentoCreateView(CreateView):
    model = FinanceiroLancamento
    form_class = LancamentoForm
    template_name = "financeiro/lancamento_form.html"
    success_url = reverse_lazy("financeiro:lancamento_list")

    def form_valid(self, form):
        lanc = form.save(commit=False)
        
        lanc.save()
 
        # DESPESA → cria FinanceiroPagar
        if lanc.categoria.tipo == "D":            
            titulo, created = FinanceiroPagar.objects.get_or_create(
                origem="LANCAMENTO",
                content_type=ContentType.objects.get_for_model(lanc),
                object_id=lanc.id,
 
                defaults={
                    "data_lancamento": lanc.data,
                    "data_vencimento": lanc.data,
                    "descricao": lanc.descricao,
                    "valor": lanc.valor,
                    "categoria": lanc.categoria,
                    "contato": lanc.contato,
                }
            )
            if not created:
                titulo.data_lancamento = lanc.data
                titulo.data_vencimento = lanc.data  # ou outra regra
                titulo.contato = lanc.contato  # Lançamentos avulsos não têm fornecedor
                titulo.descricao = lanc.descricao
                titulo.valor = lanc.valor
                titulo.categoria = lanc.categoria
                titulo.save()
        
        # RECEITA → cria FinanceiroReceber
        elif lanc.categoria.tipo == "R":
            titulo, created = FinanceiroReceber.objects.get_or_create(
                origem="LANCAMENTO",
                content_type=ContentType.objects.get_for_model(lanc),
                object_id=lanc.id,
                defaults={
                    "data_lancamento": lanc.data,
                    "data_vencimento": lanc.data,
                    "descricao": lanc.descricao,
                    "valor": lanc.valor,
                    "categoria": lanc.categoria,
                    "cliente": lanc.contato,
                }
            )  
            if not created:
                titulo.data_lancamento = lanc.data
                titulo.data_vencimento = lanc.data  # ou outra regra
                titulo.cliente = lanc.contato  # Lançamentos avulsos não têm cliente
                titulo.descricao = lanc.descricao
                titulo.valor = lanc.valor
                titulo.categoria = lanc.categoria
                titulo.save()

        return super().form_valid(form)
    
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

# Atualizar lançamento financeiro
class LancamentoUpdateView(UpdateView):
    model = FinanceiroLancamento
    form_class = LancamentoForm
    template_name = "financeiro/lancamento_form.html"
    success_url = reverse_lazy("financeiro:lancamento_list")

    def form_valid(self, form):
        lanc = form.save(commit=False)
        lanc.save()

        lancamento_ct = ContentType.objects.get_for_model(FinanceiroLancamento)
        # ============================
        # ATUALIZAR TÍTULO DE DESPESA
        # ============================
        if lanc.categoria.tipo == "D":
            try:                
                titulo = FinanceiroPagar.objects.get(
                    origem="LANCAMENTO",
                    content_type=lancamento_ct,
                    object_id=lanc.id
                )
                titulo.data_lancamento = lanc.data
                titulo.data_vencimento = lanc.data
                titulo.descricao = lanc.descricao
                titulo.valor = lanc.valor
                titulo.categoria = lanc.categoria
                titulo.save()
            except FinanceiroPagar.DoesNotExist:
                pass

        # ============================
        # ATUALIZAR TÍTULO DE RECEITA
        # ============================
        elif lanc.categoria.tipo == "R":
            try:
                titulo = FinanceiroReceber.objects.get(
                    origem="LANCAMENTO",
                    content_type=lancamento_ct,
                    object_id=lanc.id
                )
                titulo.data_lancamento = lanc.data
                titulo.data_vencimento = lanc.data
                titulo.descricao = lanc.descricao
                titulo.valor = lanc.valor
                titulo.categoria = lanc.categoria
                titulo.save()
            except FinanceiroReceber.DoesNotExist:
                pass

        return super().form_valid(form)


class LancamentoDeleteView(DeleteView):
    model = FinanceiroLancamento
    template_name = "financeiro/lancamento_confirm_delete.html"
    success_url = reverse_lazy("financeiro:lancamento_list")

    def delete(self, request, *args, **kwargs):
        lanc = self.get_object()

        if lanc.tipo == "DESPESA":
            FinanceiroPagar.objects.filter(
                origem="LANCAMENTO",
                referencia_id=lanc.id
            ).delete()
        else:
            FinanceiroReceber.objects.filter(
                origem="LANCAMENTO",
                referencia_id=lanc.id
            ).delete()

        return super().delete(request, *args, **kwargs)

