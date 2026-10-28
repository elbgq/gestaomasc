from django.db import models, transaction
from django.core.exceptions import ValidationError
from cadastros.models import Produto, Servico, Contato
from cadastros.precos import atualizar_preco_venda
from decimal import Decimal
from django.db import models
from django.conf import settings
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
    # Preenchidos na importação do XML da NF-e
    chave_acesso = models.CharField("Chave de acesso", max_length=44, unique=True, null=True, blank=True)
    xml_nfe = models.TextField("XML da NF-e", blank=True, default="")

    class Meta:
        permissions = [("importar_nfe", "Pode importar compras pelo XML da NF-e")]

    def __str__(self):
        return f"Compra {self.numero_nota} - {self.fornecedor.nome}"

    # ============================================================
    # MÉTODO: atualizar valor total
    # ============================================================
    def atualizar_valor_total(self):
        total = Decimal("0.00")
        for item in self.itens.all():
            item.save()
            total += item.valor_nota

        self.valor_total = total
        self.save()
    
    @property
    def duplicatas_conferem(self):
        # As duplicatas da nota só são usadas quando somam o total da compra
        duplicatas = list(self.duplicatas.all())
        return bool(duplicatas) and sum(d.valor for d in duplicatas) == self.valor_total

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
    
    # Número da nota como foi gravado; "—" quando não há número
    @property
    def numero_formatado(self):
        return (self.numero_nota or "").strip() or "—"



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
    quantidade = models.DecimalField(max_digits=10, decimal_places=3)
    preco_unitario = models.DecimalField(max_digits=14, decimal_places=4)
    # Dados do item na nota do fornecedor
    codigo_fornecedor = models.CharField("Código do fornecedor", max_length=60, blank=True, default="")
    ean = models.CharField("EAN", max_length=14, blank=True, default="")
    ncm = models.CharField("NCM", max_length=8, blank=True, default="")
    unidade_fornecedor = models.CharField("Unidade na nota", max_length=6, blank=True, default="")
    # Quantas unidades do produto vêm em cada unidade da nota (ex.: 1 CX = 50 UN)
    fator_conversao = models.DecimalField("Fator de conversão", max_digits=12, decimal_places=4, default=1)
    # Valores do item na NF-e que somam ou abatem do total
    valor_frete = models.DecimalField("Frete", max_digits=12, decimal_places=2, default=0)
    valor_seguro = models.DecimalField("Seguro", max_digits=12, decimal_places=2, default=0)
    valor_outras = models.DecimalField("Outras despesas", max_digits=12, decimal_places=2, default=0)
    valor_desconto = models.DecimalField("Desconto", max_digits=12, decimal_places=2, default=0)
    valor_ipi = models.DecimalField("IPI", max_digits=12, decimal_places=2, default=0)
    valor_icms_st = models.DecimalField("ICMS-ST e FCP-ST", max_digits=12, decimal_places=2, default=0)
    # Tributos já embutidos no preço; abatidos do custo só se a empresa tiver crédito (COMPRA_CREDITOS)
    valor_icms = models.DecimalField("ICMS", max_digits=12, decimal_places=2, default=0)
    valor_pis = models.DecimalField("PIS", max_digits=12, decimal_places=2, default=0)
    valor_cofins = models.DecimalField("COFINS", max_digits=12, decimal_places=2, default=0)
    # Classificação fiscal do item na NF-e, guardada para o módulo fiscal (Fase 7)
    cfop = models.CharField("CFOP", max_length=4, blank=True, default="")
    cest = models.CharField("CEST", max_length=7, blank=True, default="")
    origem = models.CharField("Origem da mercadoria", max_length=1, blank=True, default="")
    cst_icms = models.CharField("CST/CSOSN do ICMS", max_length=3, blank=True, default="")
    base_icms = models.DecimalField("Base do ICMS", max_digits=12, decimal_places=2, default=0)
    aliquota_icms = models.DecimalField("Alíquota do ICMS (%)", max_digits=7, decimal_places=4, default=0)
    base_icms_st = models.DecimalField("Base do ICMS-ST", max_digits=12, decimal_places=2, default=0)
    aliquota_ipi = models.DecimalField("Alíquota do IPI (%)", max_digits=7, decimal_places=4, default=0)
    cst_pis = models.CharField("CST do PIS", max_length=2, blank=True, default="")
    cst_cofins = models.CharField("CST da COFINS", max_length=2, blank=True, default="")
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
        self.total = (Decimal(self.quantidade) * Decimal(self.preco_unitario)).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    @property
    def valor_nota(self):
        # Quanto o item custa na nota: produtos + despesas + IPI + ST - desconto
        return (
            Decimal(self.total) + self.valor_frete + self.valor_seguro + self.valor_outras
            + self.valor_ipi + self.valor_icms_st - self.valor_desconto
        )

    @property
    def valor_creditos(self):
        from django.conf import settings
        creditos = getattr(settings, "COMPRA_CREDITOS", set())
        campos = {"ICMS": self.valor_icms, "PIS": self.valor_pis, "COFINS": self.valor_cofins, "IPI": self.valor_ipi}
        return sum((valor for nome, valor in campos.items() if nome in creditos), Decimal("0"))

    @property
    def custo_total(self):
        return self.valor_nota - self.valor_creditos

    @property
    def quantidade_estoque(self):
        return Decimal(self.quantidade) * Decimal(self.fator_conversao or 1)

    @property
    def custo_unitario_estoque(self):
        if not self.quantidade_estoque:
            return Decimal("0")
        return self.custo_total / self.quantidade_estoque


# Duplicatas (parcelas) informadas pelo fornecedor na NF-e (grupo cobr/dup)
class CompraDuplicata(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="duplicatas")
    numero = models.CharField("Número", max_length=60, blank=True, default="")
    vencimento = models.DateField("Vencimento")
    valor = models.DecimalField("Valor", max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["vencimento", "id"]

    def __str__(self):
        return f"{self.numero} {self.vencimento:%d/%m/%Y} {self.valor}"


# Vínculo entre o código do produto na nota do fornecedor e o produto do cadastro.
# É gravado na tela de vincular itens e reaproveitado nas próximas importações.
class ProdutoFornecedor(models.Model):
    fornecedor = models.ForeignKey("cadastros.Contato", on_delete=models.CASCADE, related_name="produtos_fornecidos")
    codigo_fornecedor = models.CharField("Código do fornecedor", max_length=60)
    ean = models.CharField("EAN", max_length=14, blank=True, default="")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="codigos_fornecedor")
    unidade_fornecedor = models.CharField("Unidade na nota", max_length=6, blank=True, default="")
    fator_conversao = models.DecimalField("Fator de conversão", max_digits=12, decimal_places=4, default=1)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produto do fornecedor"
        verbose_name_plural = "Produtos dos fornecedores"
        unique_together = [("fornecedor", "codigo_fornecedor")]

    def __str__(self):
        return f"{self.fornecedor} {self.codigo_fornecedor} → {self.produto}"


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
            
            # ESTORNO devolve quantidade sem alterar o preço médio
            if mov.tipo == "ENTRADA" and mov.origem.startswith("ESTORNO"):
                saldo += qtd

            # ENTRADA NO ESTOQUE
            elif mov.tipo == "ENTRADA":
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
        # O custo mudou: produto com preço automático acompanha
        atualizar_preco_venda(self.produto)

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
        # Usado pelo Painel (última movimentação de cada produto)
        indexes = [models.Index(fields=["produto", "data"], name="movestoque_produto_data_idx")]

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

        # Estorno devolve a quantidade sem alterar o preço médio
        if self.tipo == "ENTRADA" and self.origem.startswith("ESTORNO"):
            novo_saldo = qtd_atual + qtd_mov
            estoque.quantidade = novo_saldo
            estoque.save()

            self.saldo_apos = novo_saldo
            self.preco_medio_apos = preco_atual

        elif self.tipo == "ENTRADA":
            if preco_mov <= 0:
                raise ValidationError("Preço inválido para movimentação de estoque.")
            total_atual = qtd_atual * preco_atual
            total_novo = qtd_mov * preco_mov
            novo_saldo = qtd_atual + qtd_mov
            novo_preco_medio = (total_atual + total_novo) / novo_saldo

            estoque.quantidade = novo_saldo
            estoque.preco_medio = novo_preco_medio
            estoque.save()
            atualizar_preco_venda(self.produto)

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

    class Meta:
        permissions = [("emitir_recibo", "Pode emitir recibo de venda")]
        # Usado pelo Painel e pelos relatórios, que filtram vendas finalizadas por data
        indexes = [models.Index(fields=["status", "data_emissao"], name="venda_status_emissao_idx")]
 
    def __str__(self):
        return f"Venda #{self.id} - {self.cliente}"
    
    # Total da venda: itens (já com o desconto de cada item) - desconto da venda + acréscimo da venda
    @property
    def total_itens(self):
        return sum((item.total for item in self.itens.all()), Decimal("0.00"))

    def atualizar_total(self):
        self.total = self.total_itens - (self.desconto or 0) + (self.acrescimo or 0)
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
        permissions = [("ver_custos", "Pode ver preço de custo e CMV")]

    def __str__(self):
        return f"CMV {self.produto} - {self.quantidade} un"
    

#===============================================
# META DE FATURAMENTO (Painel)
#===============================================
class MetaFaturamento(models.Model):
    # Sempre o primeiro dia do mês
    mes = models.DateField("Mês", unique=True)
    valor = models.DecimalField("Meta de faturamento", max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-mes"]
        verbose_name = "Meta de faturamento"
        verbose_name_plural = "Metas de faturamento"

    def save(self, *args, **kwargs):
        self.mes = self.mes.replace(day=1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Meta {self.mes:%m/%Y}: {self.valor}"


#===============================================
# PÓS-VENDA (contatos, garantias, reclamações e pedidos de devolução)
#===============================================
class PosVenda(models.Model):
    TIPO_CHOICES = (
        ("contato", "Contato com o cliente"),
        ("garantia", "Garantia"),
        ("reclamacao", "Reclamação"),
        ("devolucao", "Pedido de devolução"),
    )
    STATUS_CHOICES = (
        ("aberto", "Aberto"),
        ("resolvido", "Resolvido"),
    )

    cliente = models.ForeignKey(Contato, on_delete=models.PROTECT, related_name="pos_vendas")
    venda = models.ForeignKey(Venda, on_delete=models.SET_NULL, null=True, blank=True, related_name="pos_vendas")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="contato")
    data = models.DateField("Data", default=timezone.localdate)
    descricao = models.TextField("O que aconteceu")
    retorno = models.DateField("Retornar até", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aberto")
    solucao = models.TextField("Solução", blank=True, default="")
    resolvido_em = models.DateField(null=True, blank=True, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "retorno", "-data"]
        verbose_name = "Pós-venda"
        verbose_name_plural = "Pós-venda"
        indexes = [models.Index(fields=["status", "retorno"], name="posvenda_status_retorno_idx")]

    def save(self, *args, **kwargs):
        # Guarda quando foi resolvido; reaberto, volta a ficar sem data
        if self.status == "resolvido" and not self.resolvido_em:
            self.resolvido_em = timezone.localdate()
        elif self.status != "resolvido":
            self.resolvido_em = None
        super().save(*args, **kwargs)

    def atrasado(self):
        return self.status == "aberto" and self.retorno is not None and self.retorno < timezone.localdate()

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.cliente}"
