from django import forms
from .models import Semestre


class SemestreForm(forms.Form):
    anio = forms.IntegerField(
        label="Año",
        min_value=2000,
        max_value=2099,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "Ej: 2026", "autofocus": True}
        ),
        error_messages={
            "required": "El año es obligatorio.",
            "invalid": "Ingresa un año válido.",
            "min_value": "El año debe ser mayor o igual a 2000.",
            "max_value": "El año debe ser menor o igual a 2099.",
        },
    )
    periodo = forms.ChoiceField(
        choices=[(1, "Primer semestre"), (2, "Segundo semestre")],
        label="Periodo",
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={"required": "Selecciona un periodo."},
    )
    activo = forms.BooleanField(
        label="Activo",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, semestre_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.semestre_id = semestre_id
        self.fields["periodo"].label_suffix = ""
        self.fields["activo"].label_suffix = ""

    def clean(self):
        cleaned = super().clean()
        anio = cleaned.get("anio")
        periodo = cleaned.get("periodo")

        if anio and periodo:
            qs = Semestre.objects.filter(anio=anio, periodo=periodo)
            if self.semestre_id:
                qs = qs.exclude(pk=self.semestre_id)
            if qs.exists():
                self.add_error(
                    None,
                    f"Ya existe un semestre {anio}-{periodo}.",
                )
        return cleaned
