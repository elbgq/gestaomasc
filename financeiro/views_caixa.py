from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Sum
from .models import CaixaMovimento
from django.contrib import messages
from django.views.generic import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from .models import CaixaMovimento
from django.utils import timezone
from datetime import timedelta
from financeiro.models import (
    FinanceiroReceber, FinanceiroPagar, CaixaMovimento, Caixa, CaixaAbertura, CaixaFechamento                        
)
 
# Abertura de caixa
def caixa_abrir(request, pk):
    caixa = get_object_or_404(Caixa, pk=pk)

    if request.method == "POST":
        valor = request.POST.get("valor_abertura")
        operador = request.user.username

        CaixaAbertura.objects.create(
            caixa=caixa,
            valor_abertura=valor,
            operador=operador,
            aberto=True
        )

        messages.success(request, "Caixa aberto com sucesso.")
        return redirect("financeiro:caixa_detalhe", pk=pk)

    return render(request, "financeiro/caixa_abrir.html", {"caixa": caixa})

# Fechamento de caixa
def caixa_fechar(request, pk):
    caixa = get_object_or_404(Caixa, pk=pk)
    abertura = CaixaAbertura.objects.filter(caixa=caixa, aberto=True).first()

    if not abertura:
        messages.error(request, "Não há caixa aberto para fechar.")
        return redirect("financeiro:caixa_detalhe", pk=pk)

    saldo_atual = caixa.saldo_atual()

    if request.method == "POST":
        valor_fechamento = request.POST.get("valor_fechamento")
        operador = request.user.username

        diferenca = float(valor_fechamento) - float(saldo_atual)

        CaixaFechamento.objects.create(
            abertura=abertura,
            valor_fechamento=valor_fechamento,
            operador=operador,
            diferenca=diferenca
        )

        abertura.aberto = False
        abertura.save()

        messages.success(request, "Caixa fechado com sucesso.")
        return redirect("financeiro:caixa_detalhe", pk=pk)

    return render(
        request,
        "financeiro/caixa_fechar.html",
        {"caixa": caixa, "saldo_atual": saldo_atual}
    )

# Criar Sangria de Caixa
def caixa_sangria(request, pk):
    caixa = get_object_or_404(Caixa, pk=pk)

    if request.method == "POST":
        valor = request.POST.get("valor")
        CaixaMovimento.objects.create(
            caixa=caixa,
            data=timezone.now(),
            descricao="Sangria de caixa",
            tipo="S",
            valor=valor,
            origem="MANUAL"
        )
        messages.success(request, "Sangria registrada.")
        return redirect("financeiro:caixa_detalhe", pk=pk)

    return render(request, "financeiro/caixa_sangria.html", {"caixa": caixa})

# Criar Reforço de Caixa
def caixa_reforco(request, pk):
    caixa = get_object_or_404(Caixa, pk=pk)

    if request.method == "POST":
        valor = request.POST.get("valor")
        CaixaMovimento.objects.create(
            caixa=caixa,
            data=timezone.now(),
            descricao="Reforço de caixa",
            tipo="E",
            valor=valor,
            origem="MANUAL"
        )
        messages.success(request, "Reforço registrado.")
        return redirect("financeiro:caixa_detalhe", pk=pk)

    return render(request, "financeiro/caixa_reforco.html", {"caixa": caixa})


# Registrar os caixas do sistema
def caixa_list(request):
    caixas = Caixa.objects.all().order_by("nome")
    return render(request, "financeiro/caixa_list.html", {
        "caixas": caixas
    })

# Evidenciar detalhes dos movimentos de caixa - REVISADO
def caixa_detalhe(request, pk):
    caixa = get_object_or_404(Caixa, pk=pk)
    # Verifica se há caixa aberto
    abertura = CaixaAbertura.objects.filter(caixa=caixa, aberto=True).first()
    
    # Fechamento (se existir)
    fechamento = None
    if abertura:
        fechamento = CaixaFechamento.objects.filter(abertura=abertura).first()

    # Filtros por data
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    movimentos = caixa.movimentos.all().order_by("-data", "-id")
    
    if data_inicio:
        movimentos = movimentos.filter(data__gte=data_inicio)

    if data_fim:
        movimentos = movimentos.filter(data__lte=data_fim)
 
    saldo = caixa.saldo_atual()

    return render(request, "financeiro/caixa_detalhe.html", {
        "caixa": caixa,
        "movimentos": movimentos,
        "saldo": saldo,
        "abertura": abertura,
        "fechamento": fechamento,
        "caixa_aberto": abertura is not None, # booleano seguro
        }
    )

# Histórico de movimentos de caixa
def caixa_historico(request):
    data_ini = request.GET.get("data_ini")
    data_fim = request.GET.get("data_fim")

    movimentos = CaixaMovimento.objects.all()

    if data_ini:
        movimentos = movimentos.filter(data__gte=data_ini)

    if data_fim:
        movimentos = movimentos.filter(data__lte=data_fim)

    movimentos = movimentos.order_by("-data", "id")

    total_entradas = movimentos.filter(tipo="E").aggregate(total=Sum("valor"))["total"] or 0
    total_saidas = movimentos.filter(tipo="S").aggregate(total=Sum("valor"))["total"] or 0
    saldo = total_entradas - total_saidas
    
     # Adicionando paginação
    paginator = Paginator(movimentos, 20)  # 20 itens por página
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "financeiro/caixa_historico.html", {
        "page_obj": page_obj,
        "movimentos": movimentos,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "saldo": saldo,
        "data_ini": data_ini,
        "data_fim": data_fim,
    })
     
# Detalhes do movimento de caixa
def caixa_movimento_detalhe(request, pk):
    movimento = get_object_or_404(CaixaMovimento, pk=pk)
    return render(request, "financeiro/caixa_movimento_detalhe.html", {
        "movimento": movimento
    })

# Criação de um caixa
class CaixaCreateView(CreateView):
    model = CaixaMovimento
    template_name = "financeiro/caixa_form.html"
    fields = ["data", "descricao", "tipo", "valor", "origem", "observacao"]
    success_url = reverse_lazy("financeiro:caixa_list")

    def form_valid(self, form):
        # Movimentos manuais sempre têm origem "MANUAL"
        mov = form.save(commit=False)
        mov.origem = "MANUAL"
        mov.save()
        return super().form_valid(form)
    
class CaixaUpdateView(UpdateView):
    model = CaixaMovimento
    template_name = "financeiro/caixa_form.html"
    fields = ["data", "descricao", "tipo", "valor", "origem", "observacao"]
    success_url = reverse_lazy("financeiro:caixa_list")

    def dispatch(self, request, *args, **kwargs):
        mov = self.get_object()
        if mov.origem != "MANUAL":
            messages.error(request, "Somente movimentos manuais podem ser editados.")
            return redirect("financeiro:caixa_list")
        return super().dispatch(request, *args, **kwargs)

class CaixaDeleteView(DeleteView):
    model = CaixaMovimento
    template_name = "financeiro/caixa_confirm_delete.html"
    success_url = reverse_lazy("financeiro:caixa_list")

    def dispatch(self, request, *args, **kwargs):
        mov = self.get_object()
        if mov.origem != "MANUAL":
            messages.error(request, "Somente movimentos manuais podem ser excluídos.")
            return redirect("financeiro:caixa_list")
        return super().dispatch(request, *args, **kwargs)
    
# DASHBOARD FINANCEIRO


def dashboard_financeiro(request):
    hoje = timezone.localdate()

    # Saldo atual do caixa
    entradas = CaixaMovimento.objects.filter(tipo="E").aggregate(total=Sum("valor"))["total"] or 0
    saídas = CaixaMovimento.objects.filter(tipo="S").aggregate(total=Sum("valor"))["total"] or 0
    saldo_atual = entradas - saídas

    # Entradas e saídas do mês atual
    primeiro_dia = hoje.replace(day=1)

    entradas_mes = CaixaMovimento.objects.filter(
        tipo="E",
        data__gte=primeiro_dia,
        data__lte=hoje
    ).aggregate(total=Sum("valor"))["total"] or 0

    saídas_mes = CaixaMovimento.objects.filter(
        tipo="S",
        data__gte=primeiro_dia,
        data__lte=hoje
    ).aggregate(total=Sum("valor"))["total"] or 0

    # Títulos vencidos
    vencidos = FinanceiroReceber.objects.filter(
        esta_pago=False,
        data_vencimento__lt=hoje
    )

    # Próximos vencimentos (7 dias)
    proximos = FinanceiroReceber.objects.filter(
        esta_pago=False,
        data_vencimento__gte=hoje,
        data_vencimento__lte=hoje + timedelta(days=7)
    )

    # Dados para gráfico (últimos 6 meses)
    meses = []
    entradas_graf = []
    saídas_graf = []

    for i in range(5, -1, -1):
        mes_ref = (hoje.replace(day=1) - timedelta(days=30 * i))
        mes_inicio = mes_ref.replace(day=1)
        mes_fim = (mes_inicio + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        meses.append(mes_inicio.strftime("%b/%Y"))

        entradas_graf.append(
            CaixaMovimento.objects.filter(
                tipo="E",
                data__gte=mes_inicio,
                data__lte=mes_fim
            ).aggregate(total=Sum("valor"))["total"] or 0
        )

        saídas_graf.append(
            CaixaMovimento.objects.filter(
                tipo="S",
                data__gte=mes_inicio,
                data__lte=mes_fim
            ).aggregate(total=Sum("valor"))["total"] or 0
        )

    return render(request, "financeiro/dashboard.html", {
        "saldo_atual": saldo_atual,
        "entradas_mes": entradas_mes,
        "saidas_mes": saídas_mes,
        "vencidos": vencidos,
        "proximos": proximos,
        "meses": meses,
        "entradas_graf": entradas_graf,
        "saidas_graf": saídas_graf,
    })
    

