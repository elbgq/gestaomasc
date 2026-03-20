from django.db import models
from django.utils import timezone
from django.db.models import Sum, F
from decimal import Decimal
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum, Case, When, DecimalField, Value




#====================================
# Models de FinanceiroCategoria
#====================================
class FinanceiroCategoria(models.Model):
    TIPO_CHOICES = (
        ('R', 'Receita'),
        ('D', 'Despesa'),
    )
    GRUPO_DRE_CHOICES = (
        ('RECEITA_BRUTA', 'Receita Bruta'),
        ('DESPESA_VENDAS', 'Despesas com Vendas'),
        ('DESPESA_ADM', 'Despesas Administrativas'),
        ('DESPESA_GERAIS', 'Despesas Gerais'),
        ('RECEITA_PATRIMONIAL', 'Receitas Patrimoniais'),
        ('RECEITAS_FINANCEIRAS', 'Receitas Financeiras'),
        ('DESPESAS_FINANCEIRAS', 'Despesas Financeiras'),
        ("ICMS", "ICMS"),
        ("ISS", "ISS"),
        ("PIS", "PIS"),
        ("COFINS", "COFINS"),
        ("IRPJ", "IRPJ"),
        ("CSLL", "CSLL"),
    )

    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=1, choices=TIPO_CHOICES)
    grupo_dre = models.CharField(
        max_length=30,
        choices=GRUPO_DRE_CHOICES,
        null=True,
        blank=True,
        help_text="Define onde esta categoria aparece no DRE",
        verbose_name="Grupo DRE"
    )

    class Meta:
        verbose_name = "Categoria Financeira"
        verbose_name_plural = "Categorias Financeiras"

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()})"

#====================================
# Models de FinanceiroLancamento
#==================================
class FinanceiroLancamento(models.Model):
    
    data = models.DateField()
    categoria = models.ForeignKey(FinanceiroCategoria, on_delete=models.PROTECT)
    descricao = models.CharField(max_length=200)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    observacao = models.TextField(blank=True, null=True)
    contato = models.ForeignKey("cadastros.Contato", on_delete=models.PROTECT, null=True, blank=True)
    
    origem = models.CharField(max_length=20, default="LANCAMENTO")  # "LANCAMENTO", "MANUAL", etc
    referencia_id = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = "Lançamento Financeiro"
        verbose_name_plural = "Lançamentos Financeiros"
        
    def __str__(self):
        return f"{self.data} - {self.descricao} - {self.valor}"
     
    def get_titulo(self):
        lancamento_ct = ContentType.objects.get_for_model(FinanceiroLancamento)
        if self.categoria.tipo == "D":  # Despesa
            return FinanceiroPagar.objects.filter(
                origem="LANCAMENTO",
                content_type=lancamento_ct,
                object_id=self.id
            ).first()
 
        if self.categoria.tipo == "R":  # Receita
            return FinanceiroReceber.objects.filter(
                origem="LANCAMENTO",
                content_type=lancamento_ct,
                object_id=self.id
            ).first()

        return None
    
    
#====================================
# Models de FinanceiroReceber
#====================================
class FinanceiroReceber(models.Model):
    data_lancamento = models.DateField()
    data_vencimento = models.DateField()
    data_pagamento = models.DateField(blank=True, null=True)

    cliente = models.ForeignKey("cadastros.Contato", on_delete=models.PROTECT)
    descricao = models.CharField(max_length=200)

    valor = models.DecimalField(max_digits=10, decimal_places=2)
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    categoria = models.ForeignKey(FinanceiroCategoria, on_delete=models.PROTECT, null=True, blank=True)
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("pago", "Pago"),
        ("cancelado", "Cancelado"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")

    ORIGEM_CHOICES = (
        ("LANCAMENTO", "Lançamento"),
        ("MANUAL", "Manual"),
        ("VENDA", "Venda"),
        ("RECEITA", "Receita Diversa"),
    )
    origem = models.CharField(max_length=20, choices=ORIGEM_CHOICES)
    # Campos para referência genérica
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.PositiveIntegerField(null=True)
    referencia = GenericForeignKey("content_type", "object_id")

    caixa_movimento = models.ForeignKey(
        "financeiro.CaixaMovimento",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="titulos_receber"
    )
    tipo = models.CharField(max_length=1, default="R")  # Receita
 
    def esta_pago(self):
        return self.valor_pago and self.valor_pago >= self.valor
    
    def __str__(self):
        return f"{self.descricao} - {self.valor}"
    class Meta:
        verbose_name = "Conta a Receber"
        verbose_name_plural = "Contas a Receber"
    

#====================================
# Models de FinanceiroPagar
#====================================
class FinanceiroPagar(models.Model):
    data_lancamento = models.DateField()
    data_vencimento = models.DateField()
    data_pagamento = models.DateField(blank=True, null=True)

    contato = models.ForeignKey("cadastros.Contato", on_delete=models.PROTECT, null=True, blank=True)
    descricao = models.CharField(max_length=200)

    valor = models.DecimalField(max_digits=10, decimal_places=2)
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    categoria = models.ForeignKey(FinanceiroCategoria, on_delete=models.PROTECT)
    compra = models.ForeignKey("comercial.Compra", null=True, blank=True, on_delete=models.SET_NULL)
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("pago", "Pago"),
        ("cancelado", "Cancelado"),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")

    ORIGEM_CHOICES = (
        ("COMPRA", "Compra"),
        ("LANCAMENTO", "Lançamento"),
        ("MANUAL", "Manual"),
    )

    origem = models.CharField(max_length=20, choices=ORIGEM_CHOICES)
    tipo = models.CharField(max_length=1, default="D")  # Despesa
    caixa_movimento = models.ForeignKey("financeiro.CaixaMovimento", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="titulos_pagar"
    )
    # Campos para referência genérica
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.PositiveIntegerField(null=True)
    referencia = GenericForeignKey("content_type", "object_id")
    

    def esta_pago(self):
        if self.valor_pago is None:
            return False    
        return self.valor_pago >= self.valor
     
    def __str__(self):
        return f"{self.descricao} - {self.valor}"
    
    class Meta:
        verbose_name = "Conta a Pagar"
        verbose_name_plural = "Contas a Pagar"


#====================================
# Models de CaixaMovimento
#====================================
class CaixaMovimento(models.Model):
    TIPO_CHOICES = (
        ("E", "Entrada"),
        ("S", "Saída"),
    )

    ORIGEM_CHOICES = (
        ("RECEITA", "Recebimento de Título"),
        ("PAGAMENTO", "Pagamento de Título"),
        ("MANUAL", "Ajuste Manual"),
        ("COMPRA", "Compra"),
        ("TRANSFERENCIA", "Transferência"),
    )

    data = models.DateField()
    descricao = models.CharField(max_length=255)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    tipo = models.CharField(max_length=1, choices=TIPO_CHOICES) 
    origem = models.CharField(max_length=20, choices=ORIGEM_CHOICES)
    referencia_id = models.IntegerField(null=True, blank=True)
    observacao = models.TextField(blank=True, null=True)
    caixa = models.ForeignKey(
        "financeiro.Caixa",
        related_name="movimentos",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = "Movimento de Caixa"
        verbose_name_plural = "Movimentos de Caixa"
    

#====================================
# Models de Caixa
#====================================
class Caixa(models.Model):
    nome = models.CharField(max_length=50, unique=True)
    saldo_inicial = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    data_abertura = models.DateField(auto_now_add=True)
    ativo = models.BooleanField(default=True)

    def saldo_atual(self):
        # Calcula o saldo atual do caixa com apenas UMA consulta ao banco.
        totals = self.movimentos.aggregate(
            entradas=Sum(
                Case(
                    When(tipo="E", then="valor"),
                    default=Value(0),
                    output_field=DecimalField()
                )
            ),
            saidas=Sum(
                Case(
                    When(tipo="S", then="valor"),
                    default=Value(0),
                    output_field=DecimalField()
                )
            )
        )
 
        entradas = totals["entradas"] or 0
        saidas = totals["saidas"] or 0

        return self.saldo_inicial + entradas - saidas

    def __str__(self):
        return self.nome
    
#====================================
# Models de CaixaAbertura
#====================================
class CaixaAbertura(models.Model):
    caixa = models.ForeignKey(Caixa, on_delete=models.CASCADE)
    data = models.DateTimeField(auto_now_add=True)
    valor_abertura = models.DecimalField(max_digits=10, decimal_places=2)
    operador = models.CharField(max_length=100)
    aberto = models.BooleanField(default=True)

#====================================
# Models de CaixaFechamento
#====================================
class CaixaFechamento(models.Model):
    abertura = models.OneToOneField(CaixaAbertura, on_delete=models.CASCADE)
    data = models.DateTimeField(auto_now_add=True)
    valor_fechamento = models.DecimalField(max_digits=10, decimal_places=2)
    operador = models.CharField(max_length=100)
    diferenca = models.DecimalField(max_digits=10, decimal_places=2)
