"""Script de datos de demostración para el SGMSC.

Uso:
    venv/bin/python seed_demo.py

Crea de forma idempotente: semestres, salas, monitores, horarios,
asignaciones y solicitudes de cambio (pendientes/aprobadas/rechazadas),
respetando todas las restricciones del dominio.
"""
import os
import random

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sgmsc.settings")
django.setup()

from django.db import transaction

from asignaciones.models import Asignacion
from cambios.models import SolicitudCambio
from horarios.models import Horario
from salas.models import Sala
from semestres.models import Semestre
from usuarios.models import Usuario

random.seed(42)


def crear_semestres():
    # Solo el semestre vigente por calendario (oct 2026 => 2do periodo).
    datos = [
        (2026, 2, True),
    ]
    semestres = []
    for anio, periodo, activo in datos:
        s, _ = Semestre.objects.get_or_create(
            anio=anio, periodo=periodo, defaults={"activo": activo}
        )
        if s.activo != activo:
            s.activo = activo
            s.save(update_fields=["activo"])
        semestres.append(s)
    return semestres


def crear_salas():
    datos = [
        ("LAB-101", "Laboratorio de Computación 1", 35),
        ("LAB-102", "Laboratorio de Computación 2", 35),
        ("LAB-201", "Laboratorio de Redes", 25),
        ("LAB-202", "Laboratorio de Electrónica", 25),
        ("SAL-A3", "Auditorio A-3", 80),
        ("SAL-B1", "Aula B-1", 45),
    ]
    salas = []
    for codigo, nombre, capacidad in datos:
        sala, _ = Sala.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre, "capacidad": capacidad}
        )
        salas.append(sala)
    return salas


def crear_monitores():
    base, creada = Usuario.objects.get_or_create(
        email="monitor@sgmsc.local",
        defaults={
            "username": "monitor1",
            "cedula": "0000000002",
            "rol": Usuario.MONITOR,
            "first_name": "Monitor",
            "last_name": "Demo",
        },
    )
    if creada:
        base.set_password("Monitor1234*")
        base.save()

    nombres = [
        ("Andrés", "García"), ("Beatriz", "López"), ("Camilo", "Rodríguez"),
        ("Daniela", "Martínez"), ("Esteban", "Hernández"), ("Fernanda", "Gómez"),
        ("Gonzalo", "Díaz"), ("Valentina", "Ruiz"), ("Héctor", "Moreno"),
        ("Laura", "Álvarez"), ("Mauricio", "Jiménez"), ("Carolina", "Vargas"),
    ]
    monitores = [base]
    for i, (nombre, apellido) in enumerate(nombres, start=2):
        email = f"monitor{i}@sgmsc.local"
        monitor, creada = Usuario.objects.get_or_create(
            email=email,
            defaults={
                "username": f"monitor{i}",
                "cedula": f"10000{i:06d}",
                "rol": Usuario.MONITOR,
                "first_name": nombre,
                "last_name": apellido,
                "telefono": f"300{i:07d}",
            },
        )
        if creada:
            monitor.set_password("Monitor1234*")
            monitor.save()
        monitores.append(monitor)
    return monitores


def crear_horarios(salas):
    """Bloques por sala: 4 franjas diarias (Lun-Sáb)."""
    franjas = [
        (7, 0, 11, 0),   # mañana temprano
        (11, 0, 15, 0),  # medio día
        (15, 0, 19, 0),  # tarde
        (19, 0, 22, 0),  # noche
    ]
    horarios = []
    for sala in salas:
        for dia in range(1, 7):  # Lunes a Sábado
            for h1, m1, h2, m2 in franjas:
                horario, _ = Horario.objects.get_or_create(
                    sala=sala,
                    dia_semana=dia,
                    hora_inicio=f"{h1:02d}:{m1:02d}",
                    hora_fin=f"{h2:02d}:{m2:02d}",
                )
                horarios.append(horario)
    return horarios


def crear_asignaciones(monitores, horarios, semestre):
    """Asigna monitores a horarios del semestre activo sin cruces de horario."""
    asignaciones = []
    # Agenda por monitor: lista de (dia, inicio, fin) para evitar solapes
    agenda = {m.id: [] for m in monitores}

    for horario in sorted(horarios, key=lambda h: (h.dia_semana, h.hora_inicio)):
        candidatos = [
            m for m in monitores
            if all(
                not (h_dia == horario.dia_semana and h_ini < horario.hora_fin and h_fin > horario.hora_inicio)
                for h_dia, h_ini, h_fin in agenda[m.id]
            )
        ]
        # Asignar solo a ~60% de los horarios para que queden espacios libres
        if not candidatos or random.random() > 0.6:
            continue
        monitor = random.choice(candidatos)
        asignacion, creada = Asignacion.objects.get_or_create(
            horario=horario,
            semestre=semestre,
            defaults={"monitor": monitor},
        )
        if creada:
            agenda[monitor.id].append(
                (horario.dia_semana, horario.hora_inicio, horario.hora_fin)
            )
            asignaciones.append(asignacion)
    return asignaciones


def crear_solicitudes(asignaciones, monitores, admin):
    """Genera solicitudes de cambio en los tres estados posibles."""
    pendientes = 0
    generadas = 0
    for asignacion in random.sample(asignaciones, min(8, len(asignaciones))):
        solicitante = asignacion.monitor
        # Reemplazo: otro monitor sin conflicto en ese horario
        candidatos = [
            m for m in monitores
            if m.id != solicitante.id and not Asignacion.objects.filter(
                monitor=m,
                semestre=asignacion.semestre,
                horario__dia_semana=asignacion.horario.dia_semana,
                horario__hora_inicio__lt=asignacion.horario.hora_fin,
                horario__hora_fin__gt=asignacion.horario.hora_inicio,
            ).exists()
        ]
        if not candidatos:
            continue

        estado = random.choices(
            [SolicitudCambio.PENDIENTE, SolicitudCambio.APROBADA, SolicitudCambio.RECHAZADA],
            weights=[4, 3, 3],
        )[0]
        # Solo una solicitud pendiente por asignación
        if estado == SolicitudCambio.PENDIENTE and asignacion.solicitudes.filter(
            estado=SolicitudCambio.PENDIENTE
        ).exists():
            continue
        if estado == SolicitudCambio.PENDIENTE:
            pendientes += 1
        elif pendientes == 0 and generadas == len(asignaciones) - 1:
            estado = SolicitudCambio.PENDIENTE  # garantizar al menos una pendiente

        solicitud = SolicitudCambio(
            asignacion=asignacion,
            solicitante=solicitante,
            monitor_reemplazo=random.choice(candidatos),
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo=random.choice(
                [
                    "Cita médica en el horario del turno.",
                    "Examen programado en otra asignatura.",
                    "Compromiso familiar previo.",
                    "Participación en congreso universitario.",
                    "Trámites personales de índole administrativa.",
                ]
            ),
            estado=estado,
        )
        if estado != SolicitudCambio.PENDIENTE:
            # validate=False evita restricciones de "pendiente" al cerrar
            solicitud.respuesta = random.choice(
                [
                    "Se aprobó el cambio, el reemplazo fue notificado por correo.",
                    "Cambio rechazado por indisponibilidad del monitor reemplazo.",
                ]
            ) if estado == SolicitudCambio.APROBADA else (
                "Rechazada: el monitor reemplazo presenta un conflicto de agenda no detectado previamente."
            )
            solicitud.respondido_por = admin
            solicitud.save(validate=False)
        else:
            solicitud.save()
        generadas += 1


@transaction.atomic
def main():
    admin = Usuario.objects.get(email="admin@sgmsc.local")
    semestres = crear_semestres()
    salas = crear_salas()
    monitores = crear_monitores()
    horarios = crear_horarios(salas)
    activo = Semestre.objects.get(activo=True)
    asignaciones = crear_asignaciones(monitores, horarios, activo)

    if not SolicitudCambio.objects.exists():
        crear_solicitudes(asignaciones, monitores, admin)

    print("=== Datos de prueba ===")
    print(f"Semestres:    {Semestre.objects.count()}")
    print(f"Salas:        {Sala.objects.count()}")
    print(f"Monitores:    {Usuario.objects.filter(rol='monitor').count()}")
    print(f"Horarios:     {Horario.objects.count()}")
    print(f"Asignaciones: {Asignacion.objects.count()}")
    print(f"Solicitudes:  {SolicitudCambio.objects.count()}")


if __name__ == "__main__":
    main()
