# comercial/views/views_posvenda.py
#
# Pós-venda (contatos, garantias, reclamações e pedidos de devolução) e metas de faturamento.
# Os dois alimentam o Painel: o pós-venda no bloco Clientes, a meta no bloco Vendas.
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from comercial.forms import MetaFaturamentoForm, PosVendaForm
from comercial.models import MetaFaturamento, PosVenda, Venda

#====================================
# PÓS-VENDA
#====================================

def posvenda_list(request):
    hoje = timezone.localdate()
    status = request.GET.get("status", "aberto")
    tipo = request.GET.get("tipo", "")
    q = request.GET.get("q", "").strip()

    qs = PosVenda.objects.select_related("cliente", "venda")
    if status in ("aberto", "resolvido"):
        qs = qs.filter(status=status)
    if status == "atrasado":
        qs = qs.filter(status="aberto", retorno__lt=hoje)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if q:
        qs = qs.filter(Q(cliente__nome__icontains=q) | Q(descricao__icontains=q))

    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "comercial/posvenda_list.html", {
        "page_obj": Paginator(qs, 20).get_page(request.GET.get("page")),
        "status": status, "tipo": tipo, "q": q,
        "tipos": PosVenda.TIPO_CHOICES,
        "hoje": hoje,
        "params": params.urlencode(),
    })


def _salvar_posvenda(request, instancia=None):
    inicial = {}
    if instancia is None:
        # Aberto a partir de uma venda: já vem com o cliente e a venda
        venda = Venda.objects.filter(pk=request.GET.get("venda")).first() if request.GET.get("venda") else None
        if venda:
            inicial = {"venda": venda.pk, "cliente": venda.cliente_id}
        elif request.GET.get("cliente"):
            inicial = {"cliente": request.GET.get("cliente")}

    form = PosVendaForm(request.POST or None, instance=instancia, initial=inicial)
    if request.method == "POST" and form.is_valid():
        registro = form.save(commit=False)
        if registro.usuario_id is None:
            registro.usuario = request.user
        registro.save()
        cache.clear()  # o Painel mostra o pós-venda na hora
        messages.success(request, "Pós-venda salvo.")
        return redirect("comercial:posvenda_list")
    return render(request, "comercial/posvenda_form.html", {"form": form, "objeto": instancia})


def posvenda_criar(request):
    return _salvar_posvenda(request)


def posvenda_editar(request, pk):
    return _salvar_posvenda(request, get_object_or_404(PosVenda, pk=pk))


#====================================
# METAS DE FATURAMENTO
#====================================

def meta_list(request):
    return render(request, "comercial/meta_list.html", {"metas": MetaFaturamento.objects.all()})


def _salvar_meta(request, instancia=None):
    inicial = {} if instancia else {"mes": timezone.localdate().replace(day=1)}
    form = MetaFaturamentoForm(request.POST or None, instance=instancia, initial=inicial)
    if request.method == "POST" and form.is_valid():
        form.save()
        # O Painel guarda os números por 5 minutos; a meta nova aparece na hora
        cache.clear()
        messages.success(request, "Meta salva.")
        return redirect("comercial:meta_list")
    return render(request, "comercial/meta_form.html", {"form": form, "objeto": instancia})


def meta_criar(request):
    return _salvar_meta(request)


def meta_editar(request, pk):
    return _salvar_meta(request, get_object_or_404(MetaFaturamento, pk=pk))
