from django.db import models, transaction
from django.core.exceptions import ValidationError
from cadastros.models import Produto, Servico, Contato
from decimal import Decimal
from django.db import models
from django.utils import timezone
from datetime import timedelta, date
from financeiro.models import FinanceiroCategoria


#=================================================
# MODELO DE COMPRAS COMPLETO COM CABEÇALHO E ITENS
#=================================================
# Cabeçalho da compra
class Compra(models.Model):
    fornecedor = models.ForeignKey("cadastros.Contato", on_delete=models.PROTECT)
    data = models.DateField()
    numero_nota = models.CharField("Número da Nota", max_length=50, blank=True, null=True)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    confirmada = models.BooleanField(default=False)
    importada = models.BooleanField(default=False)

    def __str__(self):
        return f"Compra {self.numero_nota} - {self.fornecedor.nome}"

    # ============================================================
    # MÉTODO: atualizar valor total
    # ============================================================
    def atualizar_valor_total(self):
        total = Decimal("0.00")
        for item in self.itens.all():
            item.total = Decimal(item.quantidade) * Decimal(item.preco_unitario)
            item.save()
            total += item.total

        self.valor_total = total
        self.save()
    
    # Helpers úteis
    @property
    def tem_itens_pendentes(self):
        return self.itens.filter(status="pendente").exists()

    @property
    def categoria_financeira(self):
        categoria, _ = FinanceiroCategoria.objects.get_or_create(
            nome="Compras",
            defaults={"tipo": "D"}
        )
        return categoria

    def marcar_confirmada(self):
        self.confirmada = True
        self.save()

    def marcar_estornada(self):
        self.confirmada = False
        self.save()
    
    @property
    def numero_formatado(self):
        try:
            numero_int = int(self.numero_nota)
        except (TypeError, ValueError):
            numero_int = 0
        return f"C{numero_int:06d}"



# Itens da compra
class CompraItem(models.Model):
    STATUS_CHOICES = (
        ("pendente", "Pendente"),
        ("vinculado", "Vinculado a produto"),
        ("novo_produto", "Novo produto cadastrado"),
    )
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True, blank=True)
    # 🔥 Só será usado quando a compra for importada
    descricao_importada = models.CharField("Descrição vinda do arquivo", max_length=200, null=True, blank=True)
    UNIDADES_CHOICES = [
    ('UN', 'Unidade'),
    ('KG', 'Kilograma'),
    ('LT', 'Litro'),
    ('MT', 'Metro'),
    ('CX', 'Caixa'),
    ('RL', 'Rolo'),
    ('BO', 'Bobina'),
]
    unidade = models.CharField("Unidade", max_length=3, choices=UNIDADES_CHOICES, default="UN")
    quantidade = models.IntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
 
    def __str__(self):
        return f"{self.descricao} ({self.quantidade}) {self.unidade})"
    
    @property
    def descricao(self):
        return self.descricao_importada or (self.produto.descricao if self.produto else "Item")

    @property
    def esta_vinculado(self):
        return self.status in ("vinculado", "novo_produto")

    def save(self, *args, **kwargs):
        # Garante que o total sempre estará correto
        self.total = Decimal(self.quantidade) * Decimal(self.preco_unitario)
        super().save(*args, **kwargs)


#===============================================
# MODELO DO ESTOQUE "REVISADO"
#===============================================
class Estoque(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    preco_medio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    class Meta:
        ordering = ['produto']

    def recalcular_preco_medio(self):
        # Recalcula o saldo e o preço médio com base em TODAS as movimentações do produto.
        # Usado após estornos ou edições de compras.
        movimentacoes = MovimentacaoEstoque.objects.filter(
            produto=self.produto
        ).order_by("data")

        saldo = Decimal("0.00")
        preco_medio = Decimal("0.00")

        for mov in movimentacoes:
            qtd = Decimal(mov.quantidade)
            preco = Decimal(mov.preco or 0)
            
            # ENTRADA NO ESTOQUE
            if mov.tipo == "ENTRADA":
                total_atual = saldo * preco_medio
                total_novo = qtd * preco
                saldo += qtd
                if saldo > 0:
                    preco_medio = (total_atual + total_novo) / saldo
                    
            # SAÍDA DO ESTOQUE
            elif mov.tipo == "SAIDA":
                saldo -= qtd
                if saldo < 0:
                    saldo = Decimal("0.00") # preço médio NÃO muda em saídas
                
        # Atualiza o estoque final
        self.quantidade = saldo
        self.preco_medio = preco_medio
        self.save()

#====================================
# Models de movimentações de estoques
#====================================
class MovimentacaoEstoque(models.Model):
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada'),
        ('SAIDA', 'Saída'),
    ]

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    quantidade = models.DecimalField(max_digits=10, decimal_places=3)
    preco = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    data = models.DateTimeField(auto_now_add=True)

    origem = models.CharField(max_length=50)  # Compra, Venda, Ajuste
    referencia_id = models.PositiveIntegerField(null=True, blank=True)

    saldo_apos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    preco_medio_apos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    class Meta:
        ordering = ['-data']

    # ============================================
    # MÉTODO SAVE → PROCESSA A MOVIMENTAÇÃO
    # ============================================
    def save(self, *args, **kwargs):
        is_new = self.pk is None  # Verifica se é uma nova movimentação
        
        super().save(*args, **kwargs)  # salva primeiro

        if not is_new:
            return  # Se já existia, não processa novamente (evita loops)
        
        estoque, _ = Estoque.objects.get_or_create(produto=self.produto)

        qtd_atual = Decimal(estoque.quantidade)
        preco_atual = Decimal(estoque.preco_medio)
        qtd_mov = Decimal(self.quantidade)
        preco_mov = Decimal(self.preco or 0)

        if self.tipo == "ENTRADA":
            if preco_mov <= 0:
                raise ValidationError("Preço inválido para movimentação de estoque.")
            total_atual = qtd_atual * preco_atual
            total_novo = qtd_mov * preco_mov
            novo_saldo = qtd_atual + qtd_mov
            novo_preco_medio = (total_atual + total_novo) / novo_saldo

            estoque.quantidade = novo_saldo
            estoque.preco_medio = novo_preco_medio
            estoque.save()

            self.saldo_apos = novo_saldo
            self.preco_medio_apos = novo_preco_medio

        elif self.tipo == "SAIDA":
            if qtd_mov > qtd_atual:
                raise ValueError(
                f"Estoque insuficiente para o produto {self.produto}. "
                f"Disponível: {qtd_atual}, solicitado: {qtd_mov}"
            )

            novo_saldo = qtd_atual - qtd_mov
            estoque.quantidade = novo_saldo
            estoque.save()

            self.saldo_apos = novo_saldo
            self.preco_medio_apos = preco_atual

        # Atualiza os campos saldo_apos e preco_medio_apos
        super().save(update_fields=["saldo_apos", "preco_medio_apos"])

    # ============================================
    # MÉTODO ESTORNAR → REVERTE A MOVIMENTAÇÃO
    # ============================================
    def estornar(self):
    # Reverte o efeito desta movimentação no estoque.
    # NÃO chama save() novamente para evitar duplicação.
        try:
            estoque = Estoque.objects.get(produto=self.produto)
        except Estoque.DoesNotExist:
            return  # nada a estornar

        qtd_mov = Decimal(self.quantidade)

        # Se foi ENTRADA → remove quantidade
        if self.tipo == "ENTRADA":
            estoque.quantidade -= qtd_mov

        # Se foi SAÍDA → devolve quantidade
        elif self.tipo == "SAIDA":
            estoque.quantidade += qtd_mov

        # Evita saldo negativo
        if estoque.quantidade < 0:
            estoque.quantidade = Decimal("0.00")

        estoque.save()
        estoque.recalcular_preco_medio()

 
#===============================================
# MODELO DE VENDA COMPLETO COM CABEÇALHO E ITENS
#===============================================
# Cabeçalho da venda
class Venda(models.Model):
    STATUS_CHOICES = (
        ("rascunho", "Rascunho"),
        ("finalizada", "Finalizada"),
    )
    PAGAR_CHOICES = (
        ("avista", "À Vista"),
        ("parcelado", "Parcelado"),
        ("pix", "PIX"),
        ("cartao", "Cartão"),
        ("dinheiro", "Dinheiro"),        
    )
    
    cliente = models.ForeignKey(Contato, on_delete=models.PROTECT)
    data_emissao = models.DateTimeField(default=timezone.now)
    data_finalizacao = models.DateTimeField(null=True, blank=True)
    numero = models.PositiveBigIntegerField(default=0, editable=False)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    acrescimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="rascunho",)
    observacoes = models.TextField(blank=True, null=True)
    cmv = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    forma_pagamento = models.CharField(max_length=20, choices=PAGAR_CHOICES,
        null=True, blank=True, default="avista")
    vendedor = models.ForeignKey(Contato, on_delete=models.PROTECT, null=True,
        blank=True, related_name="vendas_realizadas"
    )
 
    def __str__(self):
        return f"Venda #{self.id} - {self.cliente}"
    
    def atualizar_total(self):
        itens_total = sum(item.total for item in self.itens.all())
        self.total = itens_total
        self.save()
    
    def save(self, *args, **kwargs):
        # Gera número sequencial
        if not self.numero:
            ultimo = Venda.objects.order_by("-numero").first()
            self.numero = (ultimo.numero + 1) if ultimo else 1
        super().save(*args, **kwargs)
        
    @property
    def numero_formatado(self):
        return f"V{self.numero:06d}"
 
# Itens da venda
class VendaItem(models.Model):
    venda = models.ForeignKey(Venda, related_name="itens", on_delete=models.CASCADE)
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, null=True, blank=True)
    servico = models.ForeignKey(Servico, on_delete=models.PROTECT, null=True, blank=True)
    quantidade = models.DecimalField(max_digits=10, decimal_places=3, null=False, blank=False, default=0)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    custo_medio = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=0,
        help_text="Custo médio do produto no momento da venda"
    )
    
    @property
    def total(self):
        return (self.quantidade * self.preco_unitario) - self.desconto

    def __str__(self):
        if self.produto:
            return f"{self.produto.descricao} ({self.quantidade})"
        if self.servico:
            return f"{self.servico.descricao} ({self.quantidade})"
        return f"Item da venda #{self.venda_id}"
    
    def clean(self):
        if self.produto and self.servico:
            raise ValidationError("Um item não pode ter produto e serviço ao mesmo tempo.")
        if not self.produto and not self.servico:
            raise ValidationError("Informe um produto ou um serviço.")

    def save(self, *args, **kwargs):
        self.full_clean() # chama o clean() antes de salvar
        super().save(*args, **kwargs)
        self.venda.atualizar_total()  # atualiza o total da venda após salvar o item
    
#===============================================
# MODELO DE CUSTO DE MERCADORIAS VENDIDAS - CMV
#===============================================
class CMVItem(models.Model):
    venda = models.ForeignKey("comercial.Venda", on_delete=models.CASCADE)
    item = models.ForeignKey("comercial.VendaItem", on_delete=models.CASCADE)
    produto = models.ForeignKey("cadastros.Produto", on_delete=models.CASCADE)

    quantidade = models.DecimalField(max_digits=10, decimal_places=3)
    custo_medio = models.DecimalField(max_digits=10, decimal_places=2)
    total_cmv = models.DecimalField(max_digits=12, decimal_places=2)
 
    data = models.DateTimeField()  # data da venda
 
    class Meta:
        ordering = ["data"]
        verbose_name = "CMV do Item"
        verbose_name_plural = "CMV dos Itens"

    def __str__(self):
        return f"CMV {self.produto} - {self.quantidade} un"
    