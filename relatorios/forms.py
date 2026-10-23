from django import forms
from django.db.models import Q
from cadastros.models import Contato, Produto


# Período dos relatórios: a data inicial não pode ser depois da final
class PeriodoMixin:
    def clean(self):
        dados = super().clean()
        inicio, fim = dados.get("data_inicio"), dados.get("data_fim")
        if inicio and fim and inicio > fim:
            raise forms.ValidationError("A data inicial não pode ser depois da data final.")
        return dados


# Formulario para filtrar relatórios de compras
class FiltroComprasForm(PeriodoMixin, forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        required=False,
    )
    data_fim = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        required=False,
    )
    # Fornecedores do cadastro e quem já aparece em alguma compra
    fornecedor = forms.ModelChoiceField(
        label="Fornecedor",
        queryset=Contato.objects.filter(Q(tipo="FORNECEDOR") | Q(compra__isnull=False)).distinct().order_by("nome"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    numero_nota = forms.CharField(
        label="Número da Nota",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

# Formulario para filtrar relatórios de vendas
class FiltroVendasForm(PeriodoMixin, forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        required=False,
    )
    data_fim = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        required=False,
    )
    # Clientes do cadastro e quem já aparece em alguma venda
    cliente = forms.ModelChoiceField(
        label="Cliente",
        queryset=Contato.objects.filter(Q(tipo="CLIENTE") | Q(venda__isnull=False)).distinct().order_by("nome"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    numero_nota = forms.CharField(
        label="Número da Venda",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

# Formulario para filtrar relatórios de CMV
class FiltroCMVForm(PeriodoMixin, forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial",
        required=False,
        widget=forms.DateInput(attrs={
            "type": "date",
            "class": "form-control"
        })
    )

    data_fim = forms.DateField(
        label="Data final",
        required=False,
        widget=forms.DateInput(attrs={
            "type": "date",
            "class": "form-control"
        })
    )

    produto = forms.ModelChoiceField(
        label="Produto",
        queryset=Produto.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select"
        })
    )

# Formulario para filtrar relatórios de DRE
class FiltroDREForm(PeriodoMixin, forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    data_fim = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )

# Formulario para filtrar o relatório de movimentações de estoque
class FiltroMovimentacaoEstoqueForm(PeriodoMixin, forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    data_fim = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    produto = forms.ModelChoiceField(
        label="Produto",
        queryset=Produto.objects.order_by("descricao"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    tipo = forms.ChoiceField(
        label="Tipo",
        choices=[("", "Todos"), ("ENTRADA", "Entradas"), ("SAIDA", "Saídas")],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    origem = forms.ChoiceField(
        label="Origem",
        choices=[("", "Todas"), ("compra", "Compras"), ("venda", "Vendas"),
                 ("estorno", "Estornos de venda"), ("ajuste", "Ajustes")],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

# Formulario para filtrar o relatório de juros, multas e descontos
class FiltroJurosForm(PeriodoMixin, forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    data_fim = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    tipo = forms.ChoiceField(
        label="Mostrar",
        choices=[("", "Tudo"), ("pagar", "Contas pagas"), ("receber", "Contas recebidas")],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
