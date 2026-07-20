from django import forms

# widgets de data reutilizável
class DatePickerInput(forms.DateInput):
    input_type = "text"

    def __init__(self, **kwargs):
        kwargs.setdefault("attrs", {})
        kwargs["attrs"].update({
            "class": "form-control datepicker",
            "autocomplete": "off",
        })
        super().__init__(**kwargs)
    