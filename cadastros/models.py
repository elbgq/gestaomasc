from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.core.validators import RegexValidator, MinLengthValidator, EmailValidator, MinValueValidator

UNIDADES_CHOICES = [
    ('UN', 'Unidade'),
    ('KG', 'Kilograma'),
    ('LT', 'Litro'),
    ('MT', 'Metro'),
    ('CX', 'Caixa'),
    ('RL', 'Rolo'),
    ('BO', 'Bobina'),
]

cpf_cnpj_validator = RegexValidator(
    regex=r'^(\d{11}|\d{14})$',
    message='Informe apenas números: 11 dígitos para CPF ou 14 para CNPJ.'
)

telefone_validator = RegexValidator(
    regex=r'^\+?\d{10,15}$',
    message='Informe telefone com DDD, apenas números (pode começar com +).'
)

class Produto(models.Model):
    codor = models.CharField('CodOrigem', max_length=10, blank=True, null=False)
    descricao = models.CharField('Descrição', max_length=255)
    unidade = models.CharField('Unidade', max_length=3, choices=UNIDADES_CHOICES)
    preco_venda = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Marcado quando o administrador fixou o preço à mão: o sistema não recalcula pelo custo
    preco_manual = models.BooleanField("Preço manual", default=False)
    marca = models.CharField('Marca', max_length=100, blank=True)
    ean = models.CharField('Código de barras (EAN)', max_length=14, blank=True, default='')
    ncm = models.CharField('NCM', max_length=8, blank=True, default='')
    cest = models.CharField('CEST', max_length=7, blank=True, default='')

    estoque_minimo = models.PositiveIntegerField(default=0)
     
    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['codor']
        unique_together = [('codor', 'descricao')]
        permissions = [
            ("importar_csv", "Pode importar produtos e serviços por CSV"),
            ("revisar_precos", "Pode revisar preços de venda e alterar o markup"),
        ]

    def __str__(self):
     #   marca = f' ({self.marca})' if self.marca else ''
        return f'{self.codor} - {self.descricao}'

    # Custo médio do estoque (o mesmo usado no CMV); 0 se o produto ainda não teve compra
    @property
    def custo_medio(self):
        estoque = self.estoque_set.first()
        return Decimal(estoque.preco_medio) if estoque else Decimal("0")

    # Preço calculado pelo markup sobre o custo médio; None sem custo
    def preco_sugerido(self, config=None):
        custo = self.custo_medio
        if custo <= 0:
            return None
        config = config or ConfiguracaoPreco.atual()
        return (custo * (1 + config.markup / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # "abaixo_custo", "fora_sugerido" (só preço manual, além da tolerância) ou None
    def situacao_preco(self, config=None):
        config = config or ConfiguracaoPreco.atual()
        custo = self.custo_medio
        preco = Decimal(self.preco_venda or 0)
        if custo > 0 and preco < custo:
            return "abaixo_custo"
        sugerido = self.preco_sugerido(config)
        if self.preco_manual and sugerido:
            if abs(preco - sugerido) / sugerido * 100 > config.tolerancia:
                return "fora_sugerido"
        return None

    # Diferença do preço atual para o sugerido, em %
    def diferenca_sugerido(self, config=None):
        sugerido = self.preco_sugerido(config)
        if not sugerido:
            return None
        return ((Decimal(self.preco_venda or 0) - sugerido) / sugerido * 100).quantize(Decimal("0.1"))


# Parâmetros do preço de venda automático (um único registro, alterado na tela Revisão de preços)
class ConfiguracaoPreco(models.Model):
    markup = models.DecimalField(
        "Markup sobre o custo (%)", max_digits=6, decimal_places=2, default=Decimal("62.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    tolerancia = models.DecimalField(
        "Tolerância do aviso (%)", max_digits=5, decimal_places=2, default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Preço manual mais longe do sugerido do que isso aparece sinalizado.",
    )

    class Meta:
        verbose_name = "Configuração de preço"
        verbose_name_plural = "Configuração de preço"

    def __str__(self):
        return f"Markup {self.markup}% · tolerância {self.tolerancia}%"

    @classmethod
    def atual(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config


class Servico(models.Model):
    codsv = models.CharField('CodSv', max_length=10, blank=True, null=True)
    descricao = models.CharField('Descrição do Serviço', max_length=255)
    unidade = models.CharField('Unidade', max_length=3, choices=UNIDADES_CHOICES)
    preco_servico = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = 'Serviço'
        verbose_name_plural = 'Serviços'
        ordering = ['codsv']
        unique_together = [('codsv', 'descricao')]

    def __str__(self):
        return self.descricao
 

# CPF/CNPJ com a pontuação de costume (00.000.000/0000-00 ou 000.000.000-00);
# outro tamanho fica como veio
def formatar_documento(doc):
    digitos = "".join(c for c in (doc or "") if c.isdigit())
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return doc


class Contato(models.Model):
    TIPO_CHOICES = (
        ("FORNECEDOR", "Fornecedor"),
        ("BENEFICIARIO", "Beneficiário"),
        ("CLIENTE", "Cliente"),
        ("OUTRO", "Outro"),
    )
 
    nome = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    documento = models.CharField(max_length=30, blank=True, null=True)
    telefone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    # Categoria financeira sugerida nos lançamentos e contas deste contato
    categoria_padrao = models.ForeignKey(
        "financeiro.FinanceiroCategoria", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="contatos", verbose_name="Categoria padrão",
    )

    class Meta:
        permissions = [("unificar_contato", "Pode unificar contatos duplicados")]

    def __str__(self):
        return self.nome
