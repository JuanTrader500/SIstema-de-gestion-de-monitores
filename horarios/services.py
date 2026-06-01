from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .models import Horario


def crear_horario(*, sala_id: int, dia_semana: int, hora_inicio, hora_fin) -> Horario:
    if hora_fin <= hora_inicio:
        raise ValidationError("La hora de fin debe ser posterior a la hora de inicio.")

    horario = Horario(
        sala_id=sala_id,
        dia_semana=dia_semana,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
    )
    try:
        horario.save()
    except IntegrityError as exc:
        raise ValidationError(
            "El horario se solapa con otro existente para la misma sala y día."
        ) from exc
    return horario


def obtener_horario(id_horario: int) -> Horario:
    return Horario.objects.get(pk=id_horario)


def listar_horarios() -> list[Horario]:
    return list(Horario.objects.select_related("sala").all())


def actualizar_horario(
    *, id_horario: int, sala_id: int, dia_semana: int, hora_inicio, hora_fin
) -> Horario:
    horario = obtener_horario(id_horario)

    if hora_fin <= hora_inicio:
        raise ValidationError("La hora de fin debe ser posterior a la hora de inicio.")

    horario.sala_id = sala_id
    horario.dia_semana = dia_semana
    horario.hora_inicio = hora_inicio
    horario.hora_fin = hora_fin

    try:
        horario.save()
    except IntegrityError as exc:
        raise ValidationError(
            "El horario se solapa con otro existente para la misma sala y día."
        ) from exc
    return horario


def eliminar_horario(id_horario: int) -> None:
    from asignaciones.models import Asignacion
    if Asignacion.objects.filter(horario_id=id_horario).exists():
        raise ValidationError(
            "No se puede eliminar el horario porque tiene asignaciones activas."
        )
    Horario.objects.filter(pk=id_horario).delete()
