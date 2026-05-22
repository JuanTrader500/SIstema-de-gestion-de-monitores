from django import forms
from .models import Sala


class SalaForm(forms.Form):
    codigo = forms.CharField(
        label="Código",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ej: LAB-101",
                "autofocus": True,
            }
        ),
        error_messages={"required": "El código de la sala es obligatorio."},
    )
    nombre = forms.CharField(
        label="Nombre",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ej: Laboratorio de Cómputo",
            }
        ),
        error_messages={"required": "El nombre de la sala es obligatorio."},
    )
    capacidad = forms.IntegerField(
        label="Capacidad",
        min_value=1,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ej: 30",
            }
        ),
        error_messages={
            "required": "La capacidad es obligatoria.",
            "invalid": "Ingresa un número válido.",
            "min_value": "La capacidad debe ser mayor a cero.",
        },
    )

    def __init__(self, *args, sala_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sala_id = sala_id
        for field in self.fields.values():
            field.label_suffix = ""

    def clean_codigo(self):
        codigo = self.cleaned_data.get("codigo", "").strip().upper()
        if not codigo:
            raise forms.ValidationError("El código de la sala no puede estar vacío.")
        qs = Sala.objects.filter(codigo=codigo)
        if self.sala_id:
            qs = qs.exclude(pk=self.sala_id)
        if qs.exists():
            raise forms.ValidationError(
                f"Ya existe una sala con el código '{codigo}'."
            )
        return codigo

    def clean_nombre(self):
        nombre = self.cleaned_data.get("nombre", "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre de la sala no puede estar vacío.")
        return nombre

    def clean_capacidad(self):
        capacidad = self.cleaned_data.get("capacidad")
        if capacidad is None or capacidad <= 0:
            raise forms.ValidationError("La capacidad debe ser un número mayor a cero.")
        return capacidad
