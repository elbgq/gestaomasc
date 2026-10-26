# cadastros/forms.py
from django import forms
from .models import Produto, Servico, Contato, ConfiguracaoPreco, formatar_documento
from gestaomasc.utils.forms_mixins import MoedaMaskMixin


class ProdutoForm(MoedaMaskMixin, forms.ModelForm):
    class Meta:
        model = Produto
        fields = ["codor", "descricao", "unidade", "preco_venda", "preco_manual", "marca", "ean", "ncm", "cest"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.virou_manual = False
        # Sem compra ainda não há custo, e o preço digitado vale até a primeira compra
        self.sugerido = self.instance.preco_sugerido() if self.instance.pk else None

    # Preço diferente do sugerido é uma escolha do administrador: o produto passa a manual.
    # Automático com o preço sugerido: o sistema volta a acompanhar o custo.
    def clean(self):
        dados = super().clean()
        preco = dados.get("preco_venda")
        if self.sugerido is not None and preco is not None and not dados.get("preco_manual"):
            if preco != self.sugerido:
                dados["preco_manual"] = True
                self.virou_manual = True
        return dados


class ConfiguracaoPrecoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoPreco
        fields = ["markup", "tolerancia"]
        widgets = {
            "markup": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "tolerancia": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

class ServicoForm(MoedaMaskMixin, forms.ModelForm):
    class Meta:
        model = Servico
        fields = ["codsv", "descricao", "unidade", "categoria", "preco_servico", "preco_minimo", "preco_maximo"]

class ContatoForm(forms.ModelForm):
    class Meta:
        model = Contato
        fields = ["nome", "tipo", "documento", "telefone", "email", "categoria_padrao"]

    # Grava CPF/CNPJ sempre com a pontuação, digitado com ou sem ela
    def clean_documento(self):
        documento = (self.cleaned_data.get("documento") or "").strip()
        return formatar_documento(documento) or None


# Cadastro rápido de cliente, aberto na tela de venda (o tipo é sempre Cliente)
class ClienteRapidoForm(ContatoForm):
    class Meta(ContatoForm.Meta):
        fields = ["nome", "documento", "telefone", "email"]

    def clean(self):
        dados = super().clean()
        documento = dados.get("documento")
        if documento:
            self.existente = Contato.objects.filter(documento=documento).first()
            if self.existente:
                raise forms.ValidationError(
                    f'Já existe o contato "{self.existente.nome}" com este CPF/CNPJ.'
                )
        return dados

    def save(self, commit=True):
        self.instance.tipo = "CLIENTE"
        return super().save(commit)


# Escolha do contato que fica, ao unificar um contato duplicado
class ContatoUnificarForm(forms.Form):
    manter = forms.ModelChoiceField(
        label="Manter o contato",
        queryset=Contato.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, remover, **kwargs):
        super().__init__(*args, **kwargs)
        campo = self.fields["manter"]
        campo.queryset = Contato.objects.exclude(pk=remover.pk).order_by("nome")
        campo.label_from_instance = lambda c: f"{c.nome} ({c.documento or 'sem documento'})"
        # Sugere o contato com o mesmo nome
        mesmo_nome = campo.queryset.filter(nome__iexact=remover.nome.strip()).first()
        if mesmo_nome and not self.is_bound:
            self.initial["manter"] = mesmo_nome.pk
