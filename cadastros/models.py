from django.db import models
from django.core.validators import RegexValidator, MinLengthValidator, EmailValidator

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
    marca = models.CharField('Marca', max_length=100, blank=True)

    estoque_minimo = models.PositiveIntegerField(default=0)
     
    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['codor']
        unique_together = [('codor', 'descricao')]

    def __str__(self):
     #   marca = f' ({self.marca})' if self.marca else ''
        return f'{self.codor} - {self.descricao}'


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

    def __str__(self):
        return self.nome
