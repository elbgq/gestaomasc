from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from .models import FinanceiroCategoria

class CategoriaListView(ListView):
    model = FinanceiroCategoria
    template_name = "financeiro/categoria_list.html"
    context_object_name = "categorias"


class CategoriaCreateView(CreateView):
    model = FinanceiroCategoria
    fields = ["nome", "tipo", "grupo_dre"]
    template_name = "financeiro/categoria_form.html"
    success_url = reverse_lazy("financeiro:categoria_list")


class CategoriaUpdateView(UpdateView):
    model = FinanceiroCategoria
    fields = ["nome", "tipo", "grupo_dre"]
    template_name = "financeiro/categoria_form.html"
    success_url = reverse_lazy("financeiro:categoria_list")


class CategoriaDeleteView(DeleteView):
    model = FinanceiroCategoria
    template_name = "financeiro/categoria_confirm_delete.html"
    success_url = reverse_lazy("financeiro:categoria_list")
    