from django import forms
from usuarios.models import Usuario


class MonitorForm(forms.Form):
    first_name = forms.CharField(
        label="Nombre",
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Nombre del monitor", "autofocus": True}
        ),
        error_messages={"required": "El nombre es obligatorio."},
    )
    last_name = forms.CharField(
        label="Apellido",
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Apellido del monitor"}
        ),
        error_messages={"required": "El apellido es obligatorio."},
    )
    cedula = forms.CharField(
        label="Cédula",
        max_length=20,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Número de cédula"}
        ),
        error_messages={"required": "La cédula es obligatoria."},
    )
    email = forms.EmailField(
        label="Correo institucional",
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "correo@ejemplo.com"}
        ),
        error_messages={
            "required": "El correo es obligatorio.",
            "invalid": "Ingresa un correo válido.",
        },
    )
    telefono = forms.CharField(
        label="Teléfono",
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Número de contacto"}
        ),
    )

    def __init__(self, *args, monitor_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.monitor_id = monitor_id
        for field in self.fields.values():
            field.label_suffix = ""

    def clean_cedula(self):
        cedula = self.cleaned_data.get("cedula", "").strip()
        if not cedula:
            raise forms.ValidationError("La cédula es obligatoria.")
        qs = Usuario.objects.filter(cedula=cedula)
        if self.monitor_id:
            qs = qs.exclude(pk=self.monitor_id)
        if qs.exists():
            raise forms.ValidationError("Ya existe un monitor con esta cédula.")
        return cedula

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise forms.ValidationError("El correo es obligatorio.")
        qs = Usuario.objects.filter(email=email)
        if self.monitor_id:
            qs = qs.exclude(pk=self.monitor_id)
        if qs.exists():
            raise forms.ValidationError("Ya existe un monitor con este correo.")
        return email
