from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.core.paginator import Paginator
from .models import FinanceiroCategoria

from django.core.paginator import Paginator

class CategoriaListView(ListView):
    model = FinanceiroCategoria
    template_name = "financeiro/categoria_list.html"
    context_object_name = "categorias"
    paginate_by = None  # desativa paginação automática

    def get_queryset(self):
        return FinanceiroCategoria.objects.order_by("nome")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        categorias = context["categorias"]

        page = self.request.GET.get("page")
        paginator = Paginator(categorias, 20)
        page_obj = paginator.get_page(page)

        context.update({
            "page_obj": page_obj,
            "paginator": paginator,
            "categorias": page_obj.object_list,
            "params": self.request.GET.urlencode(),
        })

        return context

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
    