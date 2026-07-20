from django import forms
from . models import FinanceiroLancamento, FinanceiroPagar
from gestaomasc.widgets import DatePickerInput 
from financeiro.models import FinanceiroReceber


class PagarVencimentoForm(forms.ModelForm):
    class Meta:
        model = FinanceiroPagar
        fields = ["data_vencimento"]
        widgets = {
            'data_vencimento': forms.DateInput(attrs={"class": "form-control datepicker"}),
        }

# Parelamento de ecompras
class ParcelamentoCompraForm(forms.Form):
    parcelas = forms.IntegerField(min_value=1, initial=1)
    dias_entre_parcelas = forms.IntegerField(min_value=0, initial=30)
    data_inicial = forms.DateField(required=False)

  # ou o caminho correto

class LancamentoForm(forms.ModelForm): 
    class Meta:
        model = FinanceiroLancamento
        fields = [
            'data',
            'contato',
            'descricao',
            'valor',
            'categoria',
            'observacao'
        ]
        widgets = {
            'data': forms.DateInput(attrs={"class": "form-control datepicker"}),
            'descricao': forms.TextInput(attrs={'placeholder': 'Ex: Aluguel, Energia, Material de escritório'}),
            'valor': forms.NumberInput(attrs={'step': '0.01'}),
            'observacao': forms.Textarea(attrs={'rows': 3}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contato"].required = True


class FinanceiroPagarForm(forms.ModelForm):
    class Meta:
        model = FinanceiroPagar
        fields = [
            'data_lancamento',
            'data_vencimento',
            'contato',
            'descricao',
            'valor',
            'categoria',
            'origem',
        ]
        widgets = {
            'data_lancamento': forms.DateInput(attrs={"class": "form-control datepicker"}),
            'data_vencimento': forms.DateInput(attrs={"class": "form-control datepicker"}),
            'descricao': forms.TextInput(attrs={'placeholder': 'Descrição da conta'}),
            'valor': forms.NumberInput(attrs={'step': '0.01'}),
        }
    


# Formulário para Contas a Receber
class FinanceiroReceberForm(forms.ModelForm):
    class Meta:
        model = FinanceiroReceber
        fields = [
            'data_lancamento',
            'data_vencimento',
            'cliente',
            'descricao',
            'valor',
            'categoria',
        ]

        widgets = {
            'data_lancamento': forms.DateInput(attrs={"class": "form-control datepicker"}),
            'data_vencimento': forms.DateInput(attrs={"class": "form-control datepicker"}),
            'descricao': forms.TextInput(
                attrs={'placeholder': 'Descrição do recebimento'}),
            'valor': forms.NumberInput(
                attrs={'step': '0.01'}),
            'cliente': forms.Select(
                attrs={'class': 'form-select '}),
            'categoria': forms.Select(
                attrs={'class': 'form-select '}),
        }
# Formulário para quitação de títulos a receber e pagar
class QuitacaoForm(forms.Form):
    data_pagamento = forms.DateField(
        label="Data da quitação",
        widget=forms.DateInput(attrs={"class": "form-control datepicker"}),
    )
            