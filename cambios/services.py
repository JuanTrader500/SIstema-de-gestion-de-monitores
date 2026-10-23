"""Lógica de negocio para gestionar solicitudes de cambio de turno."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now

from asignaciones.models import Asignacion

from .models import SolicitudCambio


def crear_solicitud_cambio(
	*,
	asignacion,
	solicitante,
	monitor_reemplazo,
	motivo="Motivo justificado de reemplazo",
	hora_inicio_reemplazo=None,
	hora_fin_reemplazo=None,
	evidencia=None,
) -> SolicitudCambio:
	"""Crea una nueva solicitud de cambio de turno.

	Args:
		asignacion: Asignación del turno que no se podrá asistir.
		solicitante: Usuario que solicita el cambio (debe ser el dueño).
		monitor_reemplazo: Usuario que cubrirá el turno.
		motivo: Razón del cambio (mínimo 10 caracteres).
		hora_inicio_reemplazo: Hora inicial específica si es reemplazo por horas.
		hora_fin_reemplazo: Hora final específica si es reemplazo por horas.
		evidencia: Archivo de evidencia (PDF o Imagen).

	Returns:
		La SolicitudCambio creada.

	Raises:
		ValidationError: Si alguna validación del modelo falla.
	"""
	if evidencia is None:
		from django.core.files.base import ContentFile
		evidencia = ContentFile(b"%PDF-1.4 prueba", name="evidencia_automatica.pdf")

	solicitud = SolicitudCambio(
		asignacion=asignacion,
		solicitante=solicitante,
		monitor_reemplazo=monitor_reemplazo,
		hora_inicio_reemplazo=hora_inicio_reemplazo,
		hora_fin_reemplazo=hora_fin_reemplazo,
		tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
		motivo=motivo,
		evidencia=evidencia,
	)
	solicitud.save()
	return solicitud


def aprobar_solicitud(*, solicitud: SolicitudCambio, admin, respuesta=None) -> SolicitudCambio:
	"""Aprueba una solicitud de cambio de turno.

	Al aprobar, si el reemplazo es de todo el turno, se transfiere la
	asignación completa al monitor de reemplazo. Si es un reemplazo parcial
	(por horas), se divide el horario y la asignación: el monitor de
	reemplazo recibe el bloque solicitado y el monitor original conserva
	las horas restantes.

	Args:
		solicitud: Solicitud a aprobar.
		admin: Usuario administrador que aprueba.
		respuesta: Mensaje opcional de respuesta.

	Returns:
		La solicitud actualizada.

	Raises:
		ValidationError: Si la solicitud ya fue respondida o hay conflictos.
	"""
	if solicitud.estado != SolicitudCambio.PENDIENTE:
		raise ValidationError("La solicitud ya fue respondida.")

	asignacion = solicitud.asignacion
	reemplazo = solicitud.monitor_reemplazo
	solicitante = solicitud.solicitante

	inicio_eval = solicitud.get_hora_inicio
	fin_eval = solicitud.get_hora_fin

	# Verificar que el reemplazo no tenga conflicto de horario al momento de aprobar
	conflicto = Asignacion.objects.filter(
		monitor_id=reemplazo.pk,
		semestre_id=asignacion.semestre_id,
		horario__dia_semana=asignacion.horario.dia_semana,
		horario__hora_inicio__lt=fin_eval,
		horario__hora_fin__gt=inicio_eval,
	).exists()
	if conflicto:
		raise ValidationError(
			"El monitor de reemplazo ya tiene una asignación que se cruza con este horario."
		)

	with transaction.atomic():
		if not solicitud.es_reemplazo_parcial:
			# Reemplazo de turno completo
			asignacion.monitor = reemplazo
			asignacion.save()
		else:
			# Reemplazo fraccionado (por bloques de hora)
			from horarios.models import Horario
			h_orig = asignacion.horario
			t_inicio = h_orig.hora_inicio
			t_fin = h_orig.hora_fin
			rep_inicio = solicitud.hora_inicio_reemplazo
			rep_fin = solicitud.hora_fin_reemplazo
			sala = h_orig.sala
			dia = h_orig.dia_semana
			semestre = asignacion.semestre

			# 1. Ajustar el horario original al rango de reemplazo (sub-rango seguro)
			h_orig.hora_inicio = rep_inicio
			h_orig.hora_fin = rep_fin
			h_orig.save(validate=False)

			# Asignar el bloque al monitor de reemplazo
			asignacion.monitor = reemplazo
			asignacion.save()

			# 2. Si quedan horas antes del bloque, crear turno para el solicitante
			if t_inicio < rep_inicio:
				h_pre = Horario.objects.create(
					sala=sala,
					dia_semana=dia,
					hora_inicio=t_inicio,
					hora_fin=rep_inicio,
				)
				Asignacion.objects.create(
					monitor=solicitante,
					horario=h_pre,
					semestre=semestre,
				)

			# 3. Si quedan horas después del bloque, crear turno para el solicitante
			if rep_fin < t_fin:
				h_post = Horario.objects.create(
					sala=sala,
					dia_semana=dia,
					hora_inicio=rep_fin,
					hora_fin=t_fin,
				)
				Asignacion.objects.create(
					monitor=solicitante,
					horario=h_post,
					semestre=semestre,
				)

		# Registrar la aprobación en la solicitud
		solicitud.estado = SolicitudCambio.APROBADA
		solicitud.respondido_por = admin
		solicitud.respuesta = respuesta or ""
		solicitud.fecha_respuesta = now()
		solicitud.save()

	return solicitud


def rechazar_solicitud(*, solicitud: SolicitudCambio, admin, respuesta=None) -> SolicitudCambio:
	"""Rechaza una solicitud de cambio de turno.

	Args:
		solicitud: Solicitud a rechazar.
		admin: Usuario administrador que rechaza.
		respuesta: Mensaje opcional de respuesta.

	Returns:
		La solicitud actualizada.

	Raises:
		ValidationError: Si la solicitud ya fue respondida.
	"""
	if solicitud.estado != SolicitudCambio.PENDIENTE:
		raise ValidationError("La solicitud ya fue respondida.")

	solicitud.estado = SolicitudCambio.RECHAZADA
	solicitud.respondido_por = admin
	solicitud.respuesta = respuesta or ""
	solicitud.fecha_respuesta = now()
	solicitud.save()

	return solicitud
