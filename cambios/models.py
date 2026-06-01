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
	  cubra dicho espacio temporal.
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
	# Para extensibilidad futura: tipo de solicitud (por ahora solo cambio_turno)
	tipo = models.CharField(max_length=32, choices=TIPO_CHOICES)
	# Motivo del cambio
	motivo = models.TextField(blank=True)
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

		# 4. Validar que el reemplazo tenga disponibilidad en el horario (solo al crear)
		if self.estado == self.PENDIENTE and self.asignacion and self.monitor_reemplazo_id:
			from asignaciones.models import Asignacion
			conflicto = Asignacion.objects.filter(
				monitor_id=self.monitor_reemplazo_id,
				semestre_id=self.asignacion.semestre_id,
				horario__dia_semana=self.asignacion.horario.dia_semana,
				horario__hora_inicio__lt=self.asignacion.horario.hora_fin,
				horario__hora_fin__gt=self.asignacion.horario.hora_inicio,
			).exists()
			if conflicto:
				raise ValidationError({
					"monitor_reemplazo": "El monitor de reemplazo ya tiene una asignación que se cruza con este horario."
				})

		# 5. Una sola solicitud pendiente por asignación
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


