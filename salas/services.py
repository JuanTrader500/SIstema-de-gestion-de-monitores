from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .models import Sala


def crear_sala(codigo: str, nombre: str, capacidad: int) -> Sala:
    codigo = codigo.strip().upper()
    nombre = nombre.strip()

    if not codigo:
        raise ValidationError("El código de la sala no puede estar vacío.")

    if not nombre:
        raise ValidationError("El nombre de la sala no puede estar vacío.")

    if not isinstance(capacidad, int) or isinstance(capacidad, bool) or capacidad <= 0:
        raise ValidationError("La capacidad debe ser un entero mayor a cero.")

    if Sala.objects.filter(codigo=codigo).exists():
        raise ValidationError(f"Ya existe una sala con el código '{codigo}'.")

    try:
        sala = Sala.objects.create(codigo=codigo, nombre=nombre, capacidad=capacidad)
    except IntegrityError:
        raise ValidationError(f"Ya existe una sala con el código '{codigo}'.")
    return sala


def obtener_sala(id_sala: int) -> Sala:
    return Sala.objects.get(pk=id_sala)


def listar_salas() -> list[Sala]:
    return list(Sala.objects.all())


def actualizar_sala(id_sala: int, codigo: str = None, nombre: str = None, capacidad: int = None) -> Sala:
    sala = obtener_sala(id_sala)

    if codigo is not None:
        codigo = codigo.strip().upper()
        if not codigo:
            raise ValidationError("El código no puede estar vacío.")
        if Sala.objects.filter(codigo=codigo).exclude(pk=id_sala).exists():
            raise ValidationError(f"Ya existe otra sala con el código '{codigo}'.")
        sala.codigo = codigo

    if nombre is not None:
        nombre = nombre.strip()
        if not nombre:
            raise ValidationError("El nombre no puede estar vacío.")
        sala.nombre = nombre

    if capacidad is not None:
        if not isinstance(capacidad, int) or isinstance(capacidad, bool) or capacidad <= 0:
            raise ValidationError("La capacidad debe ser un entero mayor a cero.")
        sala.capacidad = capacidad

    try:
        sala.save()
    except IntegrityError:
        raise ValidationError(f"Ya existe otra sala con el código '{sala.codigo}'.")
    return sala


def eliminar_sala(id_sala: int) -> None:
    from asignaciones.models import Asignacion
    if Asignacion.objects.filter(horario__sala_id=id_sala).exists():
        raise ValidationError(
            "No se puede eliminar la sala porque tiene horarios con asignaciones activas."
        )
    sala = obtener_sala(id_sala)
    sala.delete()