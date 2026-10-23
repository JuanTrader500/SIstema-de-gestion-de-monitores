from django import forms

from asignaciones.models import Asignacion
from semestres.models import Semestre
from usuarios.models import Usuario

from .models import SolicitudCambio


class SolicitudCambioForm(forms.ModelForm):
	"""Formulario para que un monitor cree una solicitud de cambio de turno."""

	monitor_reemplazo = forms.ModelChoiceField(
		queryset=Usuario.objects.filter(rol=Usuario.MONITOR),
		label="Monitor que te reemplazará",
		widget=forms.Select(attrs={"class": "form-select", "id": "id_monitor_reemplazo"}),
		empty_label="Selecciona un compañero monitor...",
	)
	hora_inicio_reemplazo = forms.TimeField(
		required=False,
		widget=forms.HiddenInput(attrs={"id": "id_hora_inicio_reemplazo"}),
	)
	hora_fin_reemplazo = forms.TimeField(
		required=False,
		widget=forms.HiddenInput(attrs={"id": "id_hora_fin_reemplazo"}),
	)
	motivo = forms.CharField(
		label="Motivo del reemplazo",
		widget=forms.Textarea(attrs={
			"class": "form-control",
			"rows": 3,
			"placeholder": "Explica la razón por la que solicitas el reemplazo (mínimo 10 caracteres)...",
		}),
		min_length=10,
		required=True,
		error_messages={
			"required": "El motivo del reemplazo es obligatorio.",
			"min_length": "Por favor escribe al menos 10 caracteres explicando la razón.",
		},
	)
	evidencia = forms.FileField(
		label="Evidencia adjunta",
		required=True,
		widget=forms.ClearableFileInput(attrs={
			"class": "form-control",
			"accept": ".pdf,image/*",
		}),
		error_messages={
			"required": "Debes adjuntar un archivo de evidencia (PDF o imagen).",
		},
	)

	class Meta:
		model = SolicitudCambio
		fields = [
			"asignacion",
			"monitor_reemplazo",
			"hora_inicio_reemplazo",
			"hora_fin_reemplazo",
			"motivo",
			"evidencia",
		]
		widgets = {
			"asignacion": forms.Select(attrs={"class": "form-select", "id": "id_asignacion"}),
		}

	def __init__(self, *args, monitor=None, **kwargs):
		"""Inicializa el formulario con el monitor solicitante.

		Args:
			monitor: Usuario monitor que crea la solicitud.
		"""
		super().__init__(*args, **kwargs)
		self.monitor = monitor

		# Mostrar siempre el nombre completo del monitor, no su correo
		self.fields["monitor_reemplazo"].label_from_instance = (
			lambda u: u.get_full_name() or (f"{u.first_name} {u.last_name}".strip()) or u.username or u.email
		)

		if monitor:
			# Solo asignaciones del semestre activo
			semestre_activo = Semestre.objects.filter(activo=True).first()
			asignaciones_qs = (
				Asignacion.objects.filter(monitor=monitor, semestre=semestre_activo)
				if semestre_activo
				else Asignacion.objects.none()
			)
			self.fields["asignacion"].queryset = asignaciones_qs.select_related(
				"horario__sala", "semestre"
			).order_by(
				"horario__dia_semana", "horario__hora_inicio",
			)
			self.fields["asignacion"].choices = [
				(
					a.pk,
					f"{a.horario.get_dia_semana_display()} "
					f"{a.horario.hora_inicio.strftime('%H:%M')}–{a.horario.hora_fin.strftime('%H:%M')} · "
					f"{a.horario.sala.codigo}",
				)
				for a in self.fields["asignacion"].queryset
			]
			self.fields["monitor_reemplazo"].queryset = Usuario.objects.filter(
				rol=Usuario.MONITOR
			).exclude(pk=monitor.pk).order_by("first_name", "last_name", "email")
		else:
			self.fields["asignacion"].queryset = Asignacion.objects.none()

	def clean_asignacion(self):
		asignacion = self.cleaned_data.get("asignacion")
		if asignacion and self.monitor and asignacion.monitor_id != self.monitor.pk:
			raise forms.ValidationError("Solo puedes solicitar cambios de tus propias asignaciones.")
		return asignacion

	def clean_evidencia(self):
		archivo = self.cleaned_data.get("evidencia")
		if archivo:
			if archivo.size > 10 * 1024 * 1024:
				raise forms.ValidationError("El archivo no puede superar los 10 MB.")
			nombre = archivo.name.lower()
			extensiones_validas = (".pdf", ".png", ".jpg", ".jpeg", ".webp")
			if not any(nombre.endswith(ext) for ext in extensiones_validas):
				raise forms.ValidationError("Solo se permiten archivos en formato PDF o imágenes (JPG, PNG, WEBP).")
		return archivo

	def clean(self):
		cleaned_data = super().clean()
		asignacion = cleaned_data.get("asignacion")
		h_ini = cleaned_data.get("hora_inicio_reemplazo")
		h_fin = cleaned_data.get("hora_fin_reemplazo")

		if h_ini or h_fin:
			if not (h_ini and h_fin):
				raise forms.ValidationError("Debes indicar tanto la hora de inicio como la de fin del bloque.")
			if h_fin <= h_ini:
				raise forms.ValidationError("La hora de fin debe ser posterior a la hora de inicio.")
			if asignacion and asignacion.horario:
				h = asignacion.horario
				if h_ini < h.hora_inicio or h_fin > h.hora_fin:
					raise forms.ValidationError("El bloque seleccionado debe estar dentro del horario asignado.")
				# Si el bloque coincide exactamente con todo el horario, se normaliza a None (turno completo)
				if h_ini == h.hora_inicio and h_fin == h.hora_fin:
					cleaned_data["hora_inicio_reemplazo"] = None
					cleaned_data["hora_fin_reemplazo"] = None

		return cleaned_data

	def save(self, commit=True):
		instancia = super().save(commit=False)
		instancia.solicitante = self.monitor
		instancia.tipo = SolicitudCambio.TIPO_CAMBIO_TURNO
		if commit:
			instancia.save()
		return instancia


class ResponderSolicitudForm(forms.Form):
	"""Formulario para que un administrador apruebe o rechace una solicitud."""

	ESTADOS_ADMIN = [
		(SolicitudCambio.APROBADA, "Aprobar"),
		(SolicitudCambio.RECHAZADA, "Rechazar"),
	]

	estado = forms.ChoiceField(
		label="Acción",
		choices=ESTADOS_ADMIN,
		widget=forms.Select(attrs={"class": "form-select"}),
	)
	respuesta = forms.CharField(
		label="Respuesta / Comentarios",
		widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
		required=False,
	)
