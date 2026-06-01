import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils.crypto import get_random_string

from usuarios.models import Usuario

logger = logging.getLogger(__name__)


def crear_monitor(
    *, email: str, cedula: str, first_name: str, last_name: str, telefono: str = ""
) -> Usuario:
    temp_password = get_random_string(10)
    try:
        monitor = Usuario.objects.create_user(
            username=email,
            email=email,
            cedula=cedula,
            first_name=first_name,
            last_name=last_name,
            telefono=telefono,
            rol=Usuario.MONITOR,
            password=temp_password,
        )
    except IntegrityError:
        raise ValidationError("Ya existe un usuario con ese correo o cédula.")

    try:
        send_mail(
            "Bienvenido al SGM SC - Tus credenciales de acceso",
            (
                f"Hola {monitor.first_name},\n\n"
                "Tu cuenta de monitor fue creada.\n"
                f"Usuario: {monitor.email}\n"
                f"Contraseña temporal: {temp_password}\n\n"
                "Por favor inicia sesión y cambia tu contraseña lo antes posible."
            ),
            settings.EMAIL_HOST_USER,
            [monitor.email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning("No se pudo enviar el correo a %s: %s", monitor.email, exc)

    return monitor


def obtener_monitor(id_monitor: int) -> Usuario:
    return Usuario.objects.get(pk=id_monitor)


def listar_monitores() -> list[Usuario]:
    return list(Usuario.objects.filter(rol=Usuario.MONITOR).order_by("email"))


def actualizar_monitor(
    *, id_monitor: int, email: str, cedula: str, first_name: str, last_name: str, telefono: str = ""
) -> Usuario:
    monitor = obtener_monitor(id_monitor)
    monitor.email = email
    monitor.cedula = cedula
    monitor.first_name = first_name
    monitor.last_name = last_name
    monitor.telefono = telefono
    monitor.username = email
    try:
        monitor.save()
    except IntegrityError:
        raise ValidationError("Ya existe otro usuario con ese correo o cédula.")
    return monitor


def eliminar_monitor(id_monitor: int) -> None:
    from asignaciones.models import Asignacion
    if Asignacion.objects.filter(monitor_id=id_monitor).exists():
        raise ValidationError(
            "No se puede eliminar el monitor porque tiene asignaciones activas."
        )
    Usuario.objects.filter(pk=id_monitor, rol=Usuario.MONITOR).delete()
