from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.utils.timezone import now


class SolicitudCambio(models.Model):
	"""Solicitud de cambio de turno entre monitores (RF-06 / RF-07).

	- El solicitante (monitor dueño de la asignación) indica que no podrá
	  asistir a su turno y propone a otro monitor (reemplazo) para que
	  cubra dicho espacio temporal (completo o por bloques de 1 hora).
	- El sistema mantiene trazabilidad y el administrador aprueba o rechaza.
	"""

	PENDIENTE = "pendiente"
	APROBADA = "aprobada"
	RECHAZADA = "rechazada"

	TIPO_CAMBIO_TURNO = "cambio_turno"
	TIPO_CHOICES = [
		(TIPO_CAMBIO_TURNO, "Cambio de turno (Monitor Reemplazo)"),
	]

	ESTADO_CHOICES = [
		(PENDIENTE, "Pendiente"),
		(APROBADA, "Aprobada"),
		(RECHAZADA, "Rechazada"),
	]

	id_cambio = models.AutoField(primary_key=True)
	asignacion = models.ForeignKey(
		"asignaciones.Asignacion",
		on_delete=models.CASCADE,
		related_name="solicitudes",
	)
	# Monitor que solicita el cambio (debe ser dueño de la asignación)
	solicitante = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="solicitudes_cambio",
	)
	# Monitor que cubrirá el turno (obligatorio por RF-06)
	monitor_reemplazo = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="solicitudes_reemplazo",
	)
	# Horas específicas para reemplazos por bloques de 1 hora
	hora_inicio_reemplazo = models.TimeField("Hora inicio de reemplazo", null=True, blank=True)
	hora_fin_reemplazo = models.TimeField("Hora fin de reemplazo", null=True, blank=True)

	# Para extensibilidad futura: tipo de solicitud (por ahora solo cambio_turno)
	tipo = models.CharField(max_length=32, choices=TIPO_CHOICES)
	# Motivo del cambio (Obligatorio, mín. 10 caracteres)
	motivo = models.TextField("Motivo del reemplazo", blank=True)
	# Evidencia adjunta (Obligatorio por requerimiento, PDF o Imagen, máx 10 MB)
	evidencia = models.FileField(
		"Evidencia adjunta",
		upload_to="evidencias_cambios/",
		null=True,
		blank=True,
	)

	# Estado de la solicitud
	estado = models.CharField(max_length=16, choices=ESTADO_CHOICES, default=PENDIENTE)
	# Respuesta del administrador
	respuesta = models.TextField(blank=True)
	# Administrador que respondió
	respondido_por = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		null=True,
		blank=True,
		on_delete=models.PROTECT,
		related_name="respuestas_solicitud",
	)
	# Fecha de creación (timestamp del sistema, RF-06 elemento 4)
	fecha_creacion = models.DateTimeField(auto_now_add=True)
	# Fecha de respuesta (se establece automáticamente al cambiar estado)
	fecha_respuesta = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-fecha_creacion"]
		constraints = [
			UniqueConstraint(
				fields=["asignacion"],
				condition=Q(estado="pendiente"),
				name="unique_pending_solicitud_per_asignacion",
			),
		]

	@property
	def get_hora_inicio(self):
		return self.hora_inicio_reemplazo or (self.asignacion.horario.hora_inicio if self.asignacion and self.asignacion.horario else None)

	@property
	def get_hora_fin(self):
		return self.hora_fin_reemplazo or (self.asignacion.horario.hora_fin if self.asignacion and self.asignacion.horario else None)

	@property
	def es_reemplazo_parcial(self) -> bool:
		if not self.asignacion or not self.asignacion.horario or not self.hora_inicio_reemplazo or not self.hora_fin_reemplazo:
			return False
		h = self.asignacion.horario
		return (self.hora_inicio_reemplazo != h.hora_inicio) or (self.hora_fin_reemplazo != h.hora_fin)

	@property
	def duracion_reemplazo_horas(self) -> int:
		inicio = self.get_hora_inicio
		fin = self.get_hora_fin
		if inicio and fin:
			mins = (fin.hour * 60 + fin.minute) - (inicio.hour * 60 + inicio.minute)
			return max(1, mins // 60)
		return 0

	@property
	def duracion_titular_horas(self) -> int:
		if not self.asignacion or not self.asignacion.horario:
			return 0
		h = self.asignacion.horario
		total_mins = (h.hora_fin.hour * 60 + h.hora_fin.minute) - (h.hora_inicio.hour * 60 + h.hora_inicio.minute)
		total_horas = max(1, total_mins // 60)
		return max(0, total_horas - self.duracion_reemplazo_horas)

	def clean(self):
		# 1. El solicitante debe ser el dueño de la asignación (solo al crear)
		if self.estado == self.PENDIENTE and self.asignacion and self.solicitante_id and self.asignacion.monitor_id != self.solicitante_id:
			raise ValidationError({
				"solicitante": "El solicitante debe ser el monitor asignado a esta asignación."
			})

		# 2. El reemplazo no puede ser el mismo que el solicitante (RF-06, solo al crear)
		if self.estado == self.PENDIENTE and self.monitor_reemplazo_id and self.solicitante_id and self.monitor_reemplazo_id == self.solicitante_id:
			raise ValidationError({
				"monitor_reemplazo": "El monitor de reemplazo no puede ser el mismo que el solicitante."
			})

		# 3. El reemplazo debe tener rol "monitor" (solo al crear)
		if self.estado == self.PENDIENTE and self.monitor_reemplazo_id:
			rol = getattr(self.monitor_reemplazo, "rol", None)
			if rol and rol != "monitor":
				raise ValidationError({
					"monitor_reemplazo": "El reemplazo debe tener rol Monitor."
				})

		# 4. Motivo obligatorio y con al menos 10 caracteres
		if not self.motivo or len(self.motivo.strip()) < 10:
			raise ValidationError({
				"motivo": "El motivo es obligatorio y debe tener al menos 10 caracteres explicando la razón del reemplazo."
			})

		# 5. Evidencia adjunta obligatoria (PDF o Imagen, máx 10 MB)
		if not self.evidencia:
			raise ValidationError({
				"evidencia": "Debes adjuntar un archivo de evidencia (PDF o imagen)."
			})
		else:
			if hasattr(self.evidencia, "size") and self.evidencia.size > 10 * 1024 * 1024:
				raise ValidationError({
					"evidencia": "El archivo de evidencia no debe superar los 10 MB."
				})
			nombre = self.evidencia.name.lower()
			extensiones_permitidas = (".pdf", ".png", ".jpg", ".jpeg", ".webp")
			if not any(nombre.endswith(ext) for ext in extensiones_permitidas):
				raise ValidationError({
					"evidencia": "Solo se permiten archivos en formato PDF o imágenes (JPG, PNG, WEBP)."
				})

		# 6. Validar rango horario de reemplazo si se especifica
		if self.hora_inicio_reemplazo or self.hora_fin_reemplazo:
			if not (self.hora_inicio_reemplazo and self.hora_fin_reemplazo):
				raise ValidationError({
					"hora_inicio_reemplazo": "Debes especificar tanto la hora de inicio como la de fin del bloque."
				})
			if self.hora_fin_reemplazo <= self.hora_inicio_reemplazo:
				raise ValidationError({
					"hora_fin_reemplazo": "La hora de fin debe ser posterior a la hora de inicio."
				})
			if self.asignacion and self.asignacion.horario:
				h = self.asignacion.horario
				if self.hora_inicio_reemplazo < h.hora_inicio or self.hora_fin_reemplazo > h.hora_fin:
					raise ValidationError({
						"hora_inicio_reemplazo": "El bloque de reemplazo debe estar dentro del horario asignado."
					})

		# 7. Validar que el reemplazo tenga disponibilidad en el horario (solo al crear)
		if self.estado == self.PENDIENTE and self.asignacion and self.monitor_reemplazo_id:
			from asignaciones.models import Asignacion
			inicio_eval = self.hora_inicio_reemplazo or self.asignacion.horario.hora_inicio
			fin_eval = self.hora_fin_reemplazo or self.asignacion.horario.hora_fin
			conflicto = Asignacion.objects.filter(
				monitor_id=self.monitor_reemplazo_id,
				semestre_id=self.asignacion.semestre_id,
				horario__dia_semana=self.asignacion.horario.dia_semana,
				horario__hora_inicio__lt=fin_eval,
				horario__hora_fin__gt=inicio_eval,
			).exists()
			if conflicto:
				raise ValidationError({
					"monitor_reemplazo": "El monitor de reemplazo ya tiene una asignación que se cruza con este horario."
				})

		# 8. Una sola solicitud pendiente por asignación
		if self.asignacion and self.estado == self.PENDIENTE:
			qs = SolicitudCambio.objects.filter(
				asignacion=self.asignacion,
				estado=self.PENDIENTE,
			)
			if self.pk:
				qs = qs.exclude(pk=self.pk)
			if qs.exists():
				raise ValidationError("Ya existe una solicitud pendiente para esta asignación.")

	def save(self, *args, validate=True, **kwargs):
		if validate:
			self.full_clean()
		# Actualizar fecha_respuesta si cambia el estado de PENDIENTE -> APROBADA/RECHAZADA
		if self.estado != self.PENDIENTE and not self.fecha_respuesta:
			self.fecha_respuesta = now()
		super().save(*args, **kwargs)

	def __str__(self):
		return f"Solicitud de cambio ({self.asignacion}) - {self.estado}"
