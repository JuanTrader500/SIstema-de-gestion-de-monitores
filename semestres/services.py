from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .models import Semestre


def crear_semestre(*, anio: int, periodo: int, activo: bool = False) -> Semestre:
    try:
        semestre = Semestre.objects.create(anio=anio, periodo=periodo, activo=activo)
    except IntegrityError:
        raise ValidationError(f"Ya existe un semestre {anio}-{periodo}.")
    return semestre


def obtener_semestre(id_semestre: int) -> Semestre:
    return Semestre.objects.get(pk=id_semestre)


def listar_semestres() -> list[Semestre]:
    return list(Semestre.objects.all())


def actualizar_semestre(
    *, id_semestre: int, anio: int, periodo: int, activo: bool = False
) -> Semestre:
    semestre = obtener_semestre(id_semestre)
    semestre.anio = anio
    semestre.periodo = periodo
    semestre.activo = activo
    try:
        semestre.save()
    except IntegrityError:
        raise ValidationError(f"Ya existe un semestre {anio}-{periodo}.")
    return semestre


def eliminar_semestre(id_semestre: int) -> None:
    Semestre.objects.filter(pk=id_semestre).delete()
