from django import forms
from comercial.models import Compra, Venda
from cadastros.models import Contato

# Formulario para filtrar relatórios de compras
class FiltroComprasForm(forms.Form):
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
    fornecedor = forms.ModelChoiceField(
        label="Fornecedor",
        queryset=Contato.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    numero_nota = forms.CharField(
        label="Número da Nota",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

# Formulario para filtrar relatórios de vendas
class FiltroVendasForm(forms.Form):
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
    cliente = forms.ModelChoiceField(
        label="Cliente",
        queryset=Contato.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    numero_nota = forms.CharField(
        label="Número da Nota",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

from django import forms
from cadastros.models import Produto   # ajuste se o model estiver em outro app

# Formulario para filtrar relatórios de CMV
class FiltroCMVForm(forms.Form):
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
class FiltroDREForm(forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    data_fim = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    