from django import forms
from django.db.models import DecimalField, FloatField

class MoedaMaskMixin:
    """
    Adiciona automaticamente a classe 'moeda' a todos os campos
    DecimalField ou FloatField do formulário.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for nome, campo in self.fields.items():
            model_field = getattr(self._meta.model, nome, None)

            if isinstance(model_field, (DecimalField, FloatField)):
                classes = campo.widget.attrs.get("class", "")
                campo.widget.attrs["class"] = f"{classes} moeda".strip()
 