from django import forms
from decimal import Decimal, InvalidOperation
from .models import (
    Compra, CompraItem,
    Venda, VendaItem, Estoque
    )
from django.forms import inlineformset_factory, BaseInlineFormSet
from cadastros.models import Produto, Servico, Contato
from django.forms import inlineformset_factory
from gestaomasc.widgets import DatePickerInput
from gestaomasc.utils.forms_mixins import MoedaMaskMixin


# Classe bootstrap base para formulários
class BaseFormBootstrap(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

       
# comercial/forms.py
class FiltroDashboardForm(forms.Form):
    data_inicio = forms.DateField(
        label="De", required=False,
        widget=DatePickerInput()
    )
    data_fim = forms.DateField(
        label="Até", required=False,
        widget=DatePickerInput()
    )
    produto = forms.ModelChoiceField(
        label="Produto", queryset=Produto.objects.all(),
        required=False, widget=forms.Select(attrs={'class': 'form-control'})
    )
     
#===============================
# VENDAS DE PRODUTOS E SERVIÇOS
#===============================
# Formulário de venda
class VendaForm(MoedaMaskMixin, forms.ModelForm):
    class Meta:
        model = Venda
        fields = [
            "cliente",
            "data_emissao",
            "forma_pagamento",
            "observacoes",
            "desconto",
            "acrescimo",
        ]

        widgets = {
            "cliente": forms.Select(attrs={"class": "form-select "}),
            "data_emissao": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "forma_pagamento": forms.Select(attrs={"class": "form-select"}),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "desconto": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "acrescimo": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filtra apenas contatos que são clientes
        self.fields["cliente"].queryset = Contato.objects.filter(tipo="CLIENTE")

# Venda de itens - formset - Tem a função de gerenciar cada item individualmente.
class VendaItemForm(MoedaMaskMixin, forms.ModelForm):
    
    class Meta:
        model = VendaItem
        fields = ["produto", "servico", "quantidade", "preco_unitario", "desconto"]
        widgets = {
            "produto": forms.Select(attrs={
                "class": "form-select item-produto select2-produto"
            }),
            "servico": forms.Select(attrs={
                "class": "form-select item-servico select2-servico"
            }),
            "quantidade": forms.NumberInput(attrs={
                "class": "form-control item-quantidade",
                "min": "1"
            }),
            "preco_unitario": forms.NumberInput(attrs={
                "class": "form-control item-preco-unitario",
                "step": "0.01"
            }),
            "desconto": forms.NumberInput(attrs={
                "class": "form-control item-desconto",
                "step": "0.01"
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        produto = cleaned_data.get("produto")
        servico = cleaned_data.get("servico")
        quantidade = cleaned_data.get("quantidade")
        preco = cleaned_data.get("preco_unitario")
        desconto = cleaned_data.get("desconto")

        # 1. LINHA VAZIA → IGNORA
        if not produto and not servico and not quantidade and not preco and not desconto:
            return cleaned_data

        # 2. Regra: deve escolher produto OU serviço, nunca ambos
        if not produto and not servico:
            raise forms.ValidationError("Selecione um Produto ou um Serviço.")
        
        # 3. Validação de estoque para produtos
        if produto and quantidade:
            estoque = Estoque.objects.filter(produto=produto).first()

            if estoque is None:
                raise forms.ValidationError(
                    f"O produto '{produto}' não possui registro de estoque."
                )

            if quantidade > estoque.quantidade:
                raise forms.ValidationError(
                    f"Estoque insuficiente para '{produto}'. "
                    f"Disponível: {estoque.quantidade}."
                )

        return cleaned_data

# O VendaItemFormSet tem a função de gerenciar o conjunto de itens da venda,
#Criando formulários de VendaItem vinculados a uma instância de Venda.

class VendaItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        totais = {}  # produto → quantidade total solicitada

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            produto = form.cleaned_data.get("produto")
            servico = form.cleaned_data.get("servico")
            quantidade = form.cleaned_data.get("quantidade")
            preco = form.cleaned_data.get("preco_unitario")
            desconto = form.cleaned_data.get("desconto")

            # 1. LINHA TOTALMENTE VAZIA → IGNORA
            if not produto and not servico and not quantidade and not preco and not desconto:
                continue
            
            # 2. ACUMULA QUANTIDADE POR PRODUTO
            if produto and quantidade:
                totais[produto] = totais.get(produto, Decimal("0")) + Decimal(quantidade)

        # 3. VALIDAÇÃO FINAL DE ESTOQUE POR PRODUTO
        for produto, total_qtd in totais.items():
            estoque = Estoque.objects.filter(produto=produto).first()

            if estoque is None:
                raise forms.ValidationError(
                    f"O produto '{produto}' não possui registro de estoque."
                )

            if total_qtd > estoque.quantidade:
                raise forms.ValidationError(
                    f"Estoque insuficiente para '{produto}'. "
                    f"Disponível: {estoque.quantidade}, solicitado: {total_qtd}."
                )

VendaItemFormSet = inlineformset_factory(
    Venda,
    VendaItem,
    form=VendaItemForm,
    formset=VendaItemFormSet,
    extra=1,
    can_delete=True
)
#===============================
# PARCELAMENTO DE VENDAS E COMPRAS
#===============================
# Parcelamento de vendas e compras
class ParcelamentoForm(forms.Form):
    parcelas = forms.IntegerField(
        min_value=1,
        label="Número de parcelas",
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    dias_entre_parcelas = forms.IntegerField(
        min_value=1,
        label="Dias entre parcelas",
        initial=30,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    data_inicial = forms.DateField(
        required=False,
        label="Primeiro vencimento",
        widget=DatePickerInput()
    )


#===============================
# COMPRAS DE PRODUTOS
#===============================
# Formulário de compras
class CompraForm(MoedaMaskMixin, forms.ModelForm):

    class Meta:
        model = Compra
        fields = ['fornecedor', 'data', 'numero_nota', 'confirmada']
        widgets = {
            "data": DatePickerInput(),
            "numero_nota": forms.TextInput(attrs={"class": "form-control"}),
            "fornecedor": forms.Select(attrs={"class": "form-select"}),
            "confirmada": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CompraItemForm(MoedaMaskMixin, forms.ModelForm):
    class Meta:
        model = CompraItem
        fields = ['produto','unidade', 'quantidade', 'preco_unitario', 'total',  'descricao_importada']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'unidade': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control form-control-sm qtd-field'}),
            'preco_unitario': forms.NumberInput(attrs={'class': 'form-control form-control-sm preco-field', 'step': '0.01'}),
            'total': forms.NumberInput(attrs={'class': 'form-control form-control-sm total-field', 'readonly': 'readonly'}),
            'descricao_importada': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }
    def __init__(self, *args, **kwargs):
         
        # Esconde o campo descricao_importada quando a compra NÃO é importada.
        super().__init__(*args, **kwargs)

        compra = self.instance.compra if self.instance and self.instance.pk else None

        if compra and not compra.importada:
            # Remove o campo do formulário
            self.fields.pop('descricao_importada', None) 


    def clean_preco_unitario(self):
                
        valor = self.cleaned_data.get("preco_unitario")

        if valor in (None, ''):
            return None

        if isinstance(valor, str):
            valor = valor.replace(",", ".").strip()

            try:
                return Decimal(valor)
            except InvalidOperation:
                raise forms.ValidationError("Informe um número válido.")
        return valor

# campo customizado que aceita vírgula
class PrecoInput(forms.TextInput):
    def format_value(self, value):
        if isinstance(value, Decimal):
            return str(value).replace('.', ',')
        return value
    
# Formulário de compra para registrar manual de itens
CompraItemFormSet = inlineformset_factory(
    Compra,
    CompraItem,
    form=CompraItemForm,
    extra=1,
    can_delete=True
)

 
class CompraItemBaseFormSet(MoedaMaskMixin, BaseInlineFormSet):
    def clean(self):
        super().clean()

        for form in self.forms:
            if form.cleaned_data.get("DELETE"):
                continue

            produto = form.cleaned_data.get("produto")
            quantidade = form.changed_data.get("quantidade")
            preco = form.cleaned_data.get("preco_unitario")            

            # Linha totalmente vazia → marcar como DELETE
            if not produto and not quantidade and not preco:
                form.cleaned_data["DELETE"] = True
                continue
            # Se produto existe, mas preço está vazio → erro
            if produto and preco is None:
                form.add_error("preco_unitario", "Informe um número válido!")
                

# Importar compras
class ImportarCompraForm(forms.Form):
    arquivo = forms.FileField(label="Arquivo da compra (CSV)")


# Formulário de selecão de cliente
class VendaSelecionarClienteForm(forms.Form):
    contato = forms.ModelChoiceField(
        queryset=Contato.objects.all(),
        label="Cliente",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    
