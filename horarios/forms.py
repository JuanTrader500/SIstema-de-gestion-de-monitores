from django import forms
from salas.models import Sala

from .models import Horario


class HorarioForm(forms.Form):
    sala = forms.ModelChoiceField(
        queryset=Sala.objects.all(),
        label="Sala",
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={"required": "Selecciona una sala."},
    )
    dia_semana = forms.ChoiceField(
        choices=Horario.DIAS,
        label="Día",
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={"required": "Selecciona un día."},
    )
    hora_inicio = forms.TimeField(
        label="Hora inicio",
        widget=forms.TimeInput(
            attrs={"class": "form-control", "type": "time"}
        ),
        error_messages={
            "required": "La hora de inicio es obligatoria.",
            "invalid": "Ingresa una hora válida.",
        },
    )
    hora_fin = forms.TimeField(
        label="Hora fin",
        widget=forms.TimeInput(
            attrs={"class": "form-control", "type": "time"}
        ),
        error_messages={
            "required": "La hora de fin es obligatoria.",
            "invalid": "Ingresa una hora válida.",
        },
    )

    def __init__(self, *args, horario_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.horario_id = horario_id
        for field in self.fields.values():
            field.label_suffix = ""

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("hora_inicio")
        fin = cleaned.get("hora_fin")

        if inicio and fin and fin <= inicio:
            msg = "La hora de fin debe ser posterior a la hora de inicio."
            self.add_error("hora_fin", msg)

        sala = cleaned.get("sala")
        dia_semana = cleaned.get("dia_semana")

        if sala and dia_semana and inicio and fin:
            qs = Horario.objects.filter(
                sala=sala,
                dia_semana=dia_semana,
                hora_inicio__lt=fin,
                hora_fin__gt=inicio,
            )
            if self.horario_id:
                qs = qs.exclude(pk=self.horario_id)
            if qs.exists():
                self.add_error(
                    None,
                    f"Ya existe un horario que se solapa en {sala.codigo} los {dict(Horario.DIAS).get(int(dia_semana))} "
                    f"entre las {inicio.strftime('%H:%M')} y {fin.strftime('%H:%M')}.",
                )

        return cleaned
