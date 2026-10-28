from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Sum
from .models import CaixaMovimento
from django.contrib import messages
from django.views.generic import CreateView, UpdateView, DeleteView
from django.urls import reverse, reverse_lazy
from django.core.validators import MinValueValidator
from financeiro.services import saldo_geral
from .models import CaixaMovimento
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from financeiro.models import (
    FinanceiroReceber, FinanceiroPagar, CaixaMovimento, Caixa, CaixaAbertura, CaixaFechamento                        
)
 
# Lê um valor em reais digitado no formulário; devolve None se vazio ou inválido
def ler_valor(texto, permitir_zero=False):
    try:
        valor = Decimal(str(texto).replace(",", "."))
    except (InvalidOperation, TypeError):
        return None
    if valor < 0 or (valor == 0 and not permitir_zero):
        return None
    return valor.quantize(Decimal("0.01"))


# Abertura de caixa
def caixa_abrir(request, pk):
    caixa = get_object_or_404(Caixa, pk=pk)

    if CaixaAbertura.objects.filter(caixa=caixa, aberto=True).exists():
        messages.warning(request, "Este caixa já está aberto.")
        return redirect("financeiro:caixa_detalhe", pk=pk)

    saldo = caixa.saldo_atual()

    if request.method == "POST":
        valor = ler_valor(request.POST.get("valor_abertura"), permitir_zero=True)
        if valor is None:
            messages.error(request, "Informe um valor de abertura válido.")
            return redirect("financeiro:caixa_abrir", pk=pk)
        operador = request.user.username

        CaixaAbertura.objects.create(
            caixa=caixa,
            valor_abertura=valor,
            operador=operador,
            aberto=True
        )

        # O valor contado na abertura não altera o saldo; só avisa se não confere
        diferenca = valor - Decimal(saldo).quantize(Decimal("0.01"))
        if diferenca:
            messages.warning(request, f"Caixa aberto com diferença de R$ {diferenca:.2f} em relação ao saldo do sistema.")
        else:
            messages.success(request, "Caixa aberto com sucesso.")
        return redirect("financeiro:caixa_detalhe", pk=pk)

    return render(request, "financeiro/caixa_abrir.html", {"caixa": caixa, "saldo": saldo})

# Fechamento de caixa
def caixa_fechar(request, pk):
    caixa = get_object_or_404(Caixa, pk=pk)
    abertura = CaixaAbertura.objects.filter(caixa=caixa, aberto=True).first()

    if not abertura:
        messages.error(request, "Não há caixa aberto para fechar.")
        return redirect("financeiro:caixa_detalhe", pk=pk)

    saldo_atual = caixa.saldo_atual()

    if request.method == "POST":
        valor_fechamento = ler_valor(request.POST.get("valor_fechamento"), permitir_zero=True)
        if valor_fechamento is None:
            messages.error(request, "Informe o valor contado no caixa.")
            return redirect("financeiro:caixa_fechar", pk=pk)
        operador = request.user.username

        diferenca = valor_fechamento - Decimal(saldo_atual).quantize(Decimal("0.01"))

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
        valor = ler_valor(request.POST.get("valor"))
        if valor is None:
            messages.error(request, "Informe um valor de sangria maior que zero.")
            return redirect("financeiro:caixa_sangria", pk=pk)
        CaixaMovimento.objects.create(
            caixa=caixa,
            data=timezone.localdate(),
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
        valor = ler_valor(request.POST.get("valor"))
        if valor is None:
            messages.error(request, "Informe um valor de reforço maior que zero.")
            return redirect("financeiro:caixa_reforco", pk=pk)
        CaixaMovimento.objects.create(
            caixa=caixa,
            data=timezone.localdate(),
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
    saldo_atual = saldo_geral()
    
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
        "saldo_atual": saldo_atual,
        "data_ini": data_ini,
        "data_fim": data_fim,
    })
     
# Detalhes do movimento de caixa
def caixa_movimento_detalhe(request, pk):
    movimento = get_object_or_404(CaixaMovimento, pk=pk)
    return render(request, "financeiro/caixa_movimento_detalhe.html", {
        "movimento": movimento
    })

# Movimento manual no caixa (sempre ligado a um caixa)
class CaixaMovimentoFormMixin:
    model = CaixaMovimento
    template_name = "financeiro/caixa_form.html"
    fields = ["caixa", "data", "descricao", "tipo", "valor", "observacao"]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["caixa"].required = True
        form.fields["caixa"].queryset = Caixa.objects.filter(ativo=True)
        form.fields["valor"].validators.append(MinValueValidator(Decimal("0.01")))
        return form

    def get_success_url(self):
        return reverse("financeiro:caixa_detalhe", args=[self.object.caixa_id])


class CaixaCreateView(CaixaMovimentoFormMixin, CreateView):
    def get_initial(self):
        return {"caixa": Caixa.objects.filter(nome="Caixa Principal").first(), "data": timezone.localdate()}

    def form_valid(self, form):
        # Movimentos manuais sempre têm origem "MANUAL"
        form.instance.origem = "MANUAL"
        return super().form_valid(form)


class CaixaUpdateView(CaixaMovimentoFormMixin, UpdateView):
    def dispatch(self, request, *args, **kwargs):
        mov = self.get_object()
        if mov.origem != "MANUAL":
            messages.error(request, "Somente movimentos manuais podem ser editados.")
            return redirect("financeiro:caixa_movimento_detalhe", pk=mov.pk)
        return super().dispatch(request, *args, **kwargs)


class CaixaDeleteView(DeleteView):
    model = CaixaMovimento
    template_name = "financeiro/caixa_confirm_delete.html"

    def dispatch(self, request, *args, **kwargs):
        mov = self.get_object()
        if mov.origem != "MANUAL":
            messages.error(request, "Somente movimentos manuais podem ser excluídos.")
            return redirect("financeiro:caixa_movimento_detalhe", pk=mov.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        if self.object.caixa_id:
            return reverse("financeiro:caixa_detalhe", args=[self.object.caixa_id])
        return reverse("financeiro:caixa_historico")

# DASHBOARD FINANCEIRO
# O dashboard antigo virou o bloco Financeiro do Painel (relatorios/services/painel.py);
# o endereço continua funcionando e leva ao Painel.
def dashboard_financeiro(request):
    return redirect("relatorios:painel")
    

