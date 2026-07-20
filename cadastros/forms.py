# cadastros/forms.py
from django import forms
from .models import Produto, Servico, Contato
from gestaomasc.utils.forms_mixins import MoedaMaskMixin


class ProdutoForm(MoedaMaskMixin, forms.ModelForm):
    class Meta:
        model = Produto
        fields = ["codor", "descricao", "unidade", "preco_venda", "marca"]

class ServicoForm(MoedaMaskMixin, forms.ModelForm):
    class Meta:
        model = Servico
        fields = ["codsv", "descricao", "unidade", "preco_servico"]

class ContatoForm(forms.ModelForm):
    class Meta:
        model = Contato
        fields = ["nome", "tipo", "documento", "telefone", "email"]
