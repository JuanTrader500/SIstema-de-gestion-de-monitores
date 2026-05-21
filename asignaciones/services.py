from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from horarios.models import Horario
from usuarios.models import Usuario

from .models import Asignacion


@dataclass(frozen=True)
class SeleccionHorarios:
	"""Selección normalizada proveniente del hidden input `horarios`.

	- `existing_ids`: ids de `Horario` existentes seleccionados (token `h:<id>`)
	- `nuevos`: bloques a crear si no existen (token `n:<dia>|<HH:MM>|<HH:MM>`)
	"""

	existing_ids: list[int]
	nuevos: list[tuple[int, time, time]]


def _parse_hora_str(value: str) -> time:
	return datetime.strptime(value, "%H:%M").time()


def _unique_preserving_order(items: list[str]) -> list[str]:
	seen: set[str] = set()
	result: list[str] = []
	for item in items:
		if item in seen:
			continue
		seen.add(item)
		result.append(item)
	return result


def parse_seleccion_horarios(tokens: list[str]) -> SeleccionHorarios:
	"""Convierte tokens del formulario en estructuras tipadas.

	Esta función es deliberadamente estricta para evitar que un POST manipulado
	termine creando datos inconsistentes.
	"""
	if tokens is None:
		raise ValidationError("Selección de horarios inválida.")

	tokens = _unique_preserving_order([t.strip() for t in tokens if (t or "").strip()])
	if not tokens:
		return SeleccionHorarios(existing_ids=[], nuevos=[])

	existing_ids: list[int] = []
	nuevos: list[tuple[int, time, time]] = []

	for token in tokens:
		if token.startswith("h:"):
			value = token[2:]
			if not value.isdigit():
				raise ValidationError("Selección de horarios inválida.")
			existing_ids.append(int(value))
			continue

		if token.startswith("n:"):
			parts = token[2:].split("|")
			if len(parts) != 3:
				raise ValidationError("Selección de horarios inválida.")
			dia_str, inicio_str, fin_str = parts
			if not dia_str.isdigit():
				raise ValidationError("Selección de horarios inválida.")
			dia = int(dia_str)
			if dia < 1 or dia > 7:
				raise ValidationError("Selección de horarios inválida.")
			try:
				inicio = _parse_hora_str(inicio_str)
				fin = _parse_hora_str(fin_str)
			except ValueError as exc:
				raise ValidationError("Selección de horarios inválida.") from exc
			if fin <= inicio:
				raise ValidationError("Selección de horarios inválida.")
			nuevos.append((dia, inicio, fin))
			continue

		raise ValidationError("Selección de horarios inválida.")

	return SeleccionHorarios(existing_ids=existing_ids, nuevos=nuevos)


def crear_asignaciones(*, monitor, semestre, sala_id: int, seleccion_tokens: list[str]) -> int:
	"""Crea las asignaciones solicitadas de forma atómica.

	- Crea `Horario` faltantes (solo si el bloque no existe aún para la sala).
	- Crea `Asignacion` para cada bloque (Horario) en el semestre.
	
	Si algo falla (validación, duplicados, bloque ocupado, conflictos), la operación
	completa se revierte y NO deja datos parciales.
	
	Retorna el número de asignaciones creadas.
	"""
	seleccion = parse_seleccion_horarios(seleccion_tokens)
	if not seleccion.existing_ids and not seleccion.nuevos:
		raise ValidationError("Selecciona al menos un bloque horario en la grilla.")

	try:
		with transaction.atomic():
			existing_ids = seleccion.existing_ids
			nuevos = seleccion.nuevos

			horarios_existentes = list(
				Horario.objects.select_for_update().filter(
					id_horario__in=existing_ids,
					sala_id=sala_id,
				)
			)
			if len(horarios_existentes) != len(set(existing_ids)):
				raise ValidationError(
					"Hay bloques seleccionados que no pertenecen a la sala escogida."
				)

			horarios_creados: list[Horario] = []
			for dia_semana, hora_inicio, hora_fin in nuevos:
				existing = Horario.objects.select_for_update().filter(
					sala_id=sala_id,
					dia_semana=dia_semana,
					hora_inicio=hora_inicio,
					hora_fin=hora_fin,
				).first()
				if existing is not None:
					horarios_creados.append(existing)
					continue

				overlap = Horario.objects.filter(
					sala_id=sala_id,
					dia_semana=dia_semana,
					hora_inicio__lt=hora_fin,
					hora_fin__gt=hora_inicio,
				).exists()
				if overlap:
					raise ValidationError(
						"Hay un bloque seleccionado que se cruza con un horario ya existente en la sala."
					)

				try:
					horarios_creados.append(
						Horario.objects.create(
							sala_id=sala_id,
							dia_semana=dia_semana,
							hora_inicio=hora_inicio,
							hora_fin=hora_fin,
						)
					)
				except IntegrityError as exc:
					raise ValidationError(
						"No se pudieron crear algunos horarios por conflicto. Recarga la grilla y reintenta."
					) from exc

			horarios_final = {h.id_horario: h for h in (horarios_existentes + horarios_creados)}
			horario_ids = list(horarios_final.keys())

			ocupados = set(
				Asignacion.objects.filter(
					horario_id__in=horario_ids,
					semestre=semestre,
				).values_list("horario_id", flat=True)
			)
			if ocupados:
				raise ValidationError(
					"Algunos bloques ya están ocupados para ese periodo. Recarga la grilla y vuelve a intentar."
				)

			# Bloquear fila del monitor para serializar acceso por monitor+semestre.
			list(Usuario.objects.filter(pk=monitor.pk).select_for_update())

			# Validar que el monitor no tenga asignaciones en otras salas
			# que se crucen con los horarios seleccionados (única query).
			condition = Q()
			for h in horarios_final.values():
				condition |= Q(
					horario__dia_semana=h.dia_semana,
					horario__hora_inicio__lt=h.hora_fin,
					horario__hora_fin__gt=h.hora_inicio,
				)
			conflicto = Asignacion.objects.filter(
				monitor=monitor,
				semestre=semestre,
			).exclude(
				horario_id__in=horario_ids,
			).filter(condition).exists()
			if conflicto:
				raise ValidationError(
					"El monitor ya tiene asignaciones en otro(s) bloque(s) que se cruzan "
					"con los horarios seleccionados en otra sala."
				)

			creadas = 0
			for hid in horario_ids:
				try:
					Asignacion.objects.create(
						monitor=monitor,
						horario=horarios_final[hid],
						semestre=semestre,
					)
				except IntegrityError as exc:
					raise ValidationError(
						"No se pudieron guardar las asignaciones (posible conflicto). Recarga la grilla y reintenta."
					) from exc
				creadas += 1

			return creadas
	except IntegrityError as exc:
		# Fallback: cualquier IntegrityError inesperado dentro de la transacción.
		raise ValidationError(
			"No se pudo completar la operación por un conflicto en base de datos. Recarga la grilla y reintenta."
		) from exc
