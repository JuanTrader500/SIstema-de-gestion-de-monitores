"""
tests.py — app cambios

Cubre:
  - Modelo SolicitudCambio (clean: dueño, mismo solicitante/reemplazo,
    rol reemplazo, conflicto horario, una sola pendiente por asignación)
  - save() actualiza fecha_respuesta al cambiar estado
  - Service crear_solicitud_cambio
  - Service aprobar_solicitud (cambia monitor de asignación, verifica conflicto)
  - Service rechazar_solicitud
  - Vista crear_solicitud_view (monitor crea, validaciones de form)
  - Vista mis_solicitudes_view (solo ve las propias)
  - Vista lista_solicitudes_view (solo admin)
  - Vista responder_solicitud_view (aprueba/rechaza)
"""

from datetime import time

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.timezone import now

from asignaciones.models import Asignacion
from cambios.models import SolicitudCambio
from cambios import services
from horarios.models import Horario
from salas.models import Sala
from semestres.models import Semestre
from usuarios.models import Usuario


# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------

def _usuario(email, cedula, rol=Usuario.MONITOR) -> Usuario:
    return Usuario.objects.create_user(
        username=email, email=email, password="pass123",
        cedula=cedula, rol=rol, first_name="N", last_name="A",
    )


def _sala(codigo="S-101") -> Sala:
    return Sala.objects.create(codigo=codigo, nombre="Lab", capacidad=20)


def _semestre(anio=2026, periodo=1) -> Semestre:
    return Semestre.objects.create(anio=anio, periodo=periodo, activo=True)


def _horario(sala, dia=1, inicio=time(8, 0), fin=time(10, 0)) -> Horario:
    return Horario.objects.create(
        sala=sala, dia_semana=dia, hora_inicio=inicio, hora_fin=fin,
    )


def _asignacion(monitor, horario, semestre) -> Asignacion:
    return Asignacion.objects.create(
        monitor=monitor, horario=horario, semestre=semestre,
    )


class BaseTestCase(TestCase):
    """Fixtures comunes para todos los tests de cambios."""

    def setUp(self):
        self.sala = _sala()
        self.semestre = _semestre()
        self.monitor1 = _usuario("m1@u.edu", "001")
        self.monitor2 = _usuario("m2@u.edu", "002")
        self.admin = _usuario("admin@u.edu", "999", rol=Usuario.ADMIN)
        self.horario = _horario(self.sala)
        self.asignacion = _asignacion(self.monitor1, self.horario, self.semestre)


# ===========================================================================
# 1. Modelo — clean()
# ===========================================================================

class SolicitudCambioCleanTests(BaseTestCase):

    def _solicitud_base(self, **kwargs) -> SolicitudCambio:
        defaults = dict(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo="Razón",
        )
        defaults.update(kwargs)
        return SolicitudCambio(**defaults)

    def test_solicitud_valida_no_lanza_error(self):
        s = self._solicitud_base()
        try:
            s.clean()
        except ValidationError:
            self.fail("clean() lanzó ValidationError con datos válidos.")

    def test_solicitante_no_es_dueno_falla(self):
        s = self._solicitud_base(solicitante=self.monitor2)
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("solicitante", ctx.exception.message_dict)

    def test_reemplazo_igual_solicitante_falla(self):
        s = self._solicitud_base(monitor_reemplazo=self.monitor1)
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("monitor_reemplazo", ctx.exception.message_dict)

    def test_reemplazo_con_rol_admin_falla(self):
        s = self._solicitud_base(monitor_reemplazo=self.admin)
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("monitor_reemplazo", ctx.exception.message_dict)

    def test_reemplazo_con_conflicto_de_horario_falla(self):
        # monitor2 ya tiene una asignación en el mismo horario
        sala2 = _sala("S-202")
        horario2 = _horario(sala2, dia=1, inicio=time(8, 0), fin=time(10, 0))
        _asignacion(self.monitor2, horario2, self.semestre)

        s = self._solicitud_base()
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("monitor_reemplazo", ctx.exception.message_dict)

    def test_segunda_solicitud_pendiente_para_misma_asignacion_falla(self):
        # Primera solicitud pendiente guardada
        SolicitudCambio.objects.create(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo="Primera",
        )
        # Segunda intenta crearse con validate=False para llegar al clean
        s = self._solicitud_base(motivo="Segunda")
        with self.assertRaises(ValidationError):
            s.clean()


# ===========================================================================
# 2. Modelo — save() actualiza fecha_respuesta
# ===========================================================================

class SolicitudCambioSaveTests(BaseTestCase):

    def test_fecha_respuesta_se_establece_al_aprobar(self):
        s = SolicitudCambio.objects.create(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
        )
        self.assertIsNone(s.fecha_respuesta)

        s.estado = SolicitudCambio.APROBADA
        s.save(validate=False)
        s.refresh_from_db()
        self.assertIsNotNone(s.fecha_respuesta)

    def test_fecha_respuesta_no_sobreescribe_si_ya_existe(self):
        fecha_fija = now()
        s = SolicitudCambio.objects.create(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            estado=SolicitudCambio.RECHAZADA,
            fecha_respuesta=fecha_fija,
        )
        s.save(validate=False)
        s.refresh_from_db()
        self.assertEqual(s.fecha_respuesta, fecha_fija)


# ===========================================================================
# 3. Service — crear_solicitud_cambio
# ===========================================================================

class CrearSolicitudServiceTests(BaseTestCase):

    def test_crea_solicitud_correctamente(self):
        s = services.crear_solicitud_cambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            motivo="No puedo ir",
        )
        self.assertEqual(s.estado, SolicitudCambio.PENDIENTE)
        self.assertEqual(s.tipo, SolicitudCambio.TIPO_CAMBIO_TURNO)
        self.assertEqual(SolicitudCambio.objects.count(), 1)

    def test_falla_si_solicitante_no_es_dueno(self):
        with self.assertRaises(ValidationError):
            services.crear_solicitud_cambio(
                asignacion=self.asignacion,
                solicitante=self.monitor2,  # no es dueño
                monitor_reemplazo=self.monitor1,
            )

    def test_falla_si_reemplazo_igual_solicitante(self):
        with self.assertRaises(ValidationError):
            services.crear_solicitud_cambio(
                asignacion=self.asignacion,
                solicitante=self.monitor1,
                monitor_reemplazo=self.monitor1,
            )


# ===========================================================================
# 4. Service — aprobar_solicitud
# ===========================================================================

class AprobarSolicitudServiceTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.solicitud = services.crear_solicitud_cambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            motivo="Test",
        )

    def test_aprueba_y_cambia_monitor_de_asignacion(self):
        services.aprobar_solicitud(
            solicitud=self.solicitud,
            admin=self.admin,
            respuesta="Ok",
        )
        self.solicitud.refresh_from_db()
        self.asignacion.refresh_from_db()

        self.assertEqual(self.solicitud.estado, SolicitudCambio.APROBADA)
        self.assertEqual(self.asignacion.monitor, self.monitor2)
        self.assertEqual(self.solicitud.respondido_por, self.admin)
        self.assertIsNotNone(self.solicitud.fecha_respuesta)

    def test_no_puede_aprobar_solicitud_ya_respondida(self):
        self.solicitud.estado = SolicitudCambio.RECHAZADA
        self.solicitud.save(validate=False)
        with self.assertRaises(ValidationError):
            services.aprobar_solicitud(solicitud=self.solicitud, admin=self.admin)

    def test_falla_si_reemplazo_tiene_conflicto_al_momento_de_aprobar(self):
        # monitor2 adquiere conflicto antes de que se apruebe
        sala2 = _sala("S-202")
        horario2 = _horario(sala2, dia=1, inicio=time(8, 0), fin=time(10, 0))
        _asignacion(self.monitor2, horario2, self.semestre)

        with self.assertRaises(ValidationError):
            services.aprobar_solicitud(solicitud=self.solicitud, admin=self.admin)

        # La asignación original no cambia
        self.asignacion.refresh_from_db()
        self.assertEqual(self.asignacion.monitor, self.monitor1)


# ===========================================================================
# 5. Service — rechazar_solicitud
# ===========================================================================

class RechazarSolicitudServiceTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.solicitud = services.crear_solicitud_cambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
        )

    def test_rechaza_correctamente(self):
        services.rechazar_solicitud(
            solicitud=self.solicitud,
            admin=self.admin,
            respuesta="No procede",
        )
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, SolicitudCambio.RECHAZADA)
        self.assertEqual(self.solicitud.respondido_por, self.admin)
        self.assertIsNotNone(self.solicitud.fecha_respuesta)

    def test_no_puede_rechazar_solicitud_ya_respondida(self):
        self.solicitud.estado = SolicitudCambio.APROBADA
        self.solicitud.save(validate=False)
        with self.assertRaises(ValidationError):
            services.rechazar_solicitud(solicitud=self.solicitud, admin=self.admin)

    def test_asignacion_no_cambia_al_rechazar(self):
        services.rechazar_solicitud(solicitud=self.solicitud, admin=self.admin)
        self.asignacion.refresh_from_db()
        self.assertEqual(self.asignacion.monitor, self.monitor1)


# ===========================================================================
# 6. Vistas
# ===========================================================================

class CrearSolicitudViewTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.url = reverse("crear_solicitud")

    def test_anonimo_redirige_a_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_admin_recibe_403(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_monitor_puede_ver_el_form(self):
        self.client.force_login(self.monitor1)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_valido_crea_solicitud_y_redirige(self):
        self.client.force_login(self.monitor1)
        response = self.client.post(self.url, {
            "asignacion": self.asignacion.pk,
            "monitor_reemplazo": self.monitor2.pk,
            "motivo": "No puedo asistir",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SolicitudCambio.objects.count(), 1)

    def test_post_invalido_no_crea_solicitud(self):
        self.client.force_login(self.monitor1)
        response = self.client.post(self.url, {
            "asignacion": self.asignacion.pk,
            "monitor_reemplazo": self.monitor1.pk,  # mismo que solicitante
            "motivo": "Test",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SolicitudCambio.objects.count(), 0)


class MisSolicitudesViewTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.url = reverse("mis_solicitudes")

    def test_anonimo_redirige(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"/usuarios/login/?next={self.url}", fetch_redirect_response=False)

    def test_monitor_ve_solo_sus_solicitudes(self):
        # monitor1 tiene una solicitud
        SolicitudCambio.objects.create(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
        )
        self.client.force_login(self.monitor1)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["solicitudes"]), 1)

    def test_otro_monitor_no_ve_solicitudes_ajenas(self):
        SolicitudCambio.objects.create(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
        )
        self.client.force_login(self.monitor2)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["solicitudes"]), 0)


class ListaSolicitudesViewTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.url = reverse("lista_solicitudes")

    def test_monitor_recibe_403(self):
        self.client.force_login(self.monitor1)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_admin_puede_ver_todas_las_solicitudes(self):
        SolicitudCambio.objects.create(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
        )
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["solicitudes"]), 1)


class ResponderSolicitudViewTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.solicitud = SolicitudCambio.objects.create(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
        )
        self.url = reverse("responder_solicitud", args=[self.solicitud.pk])

    def test_monitor_recibe_403(self):
        self.client.force_login(self.monitor1)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_admin_puede_ver_formulario(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_admin_puede_rechazar(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {
            "estado": SolicitudCambio.RECHAZADA,
            "respuesta": "No procede",
        })
        self.assertRedirects(response, reverse("lista_solicitudes"))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, SolicitudCambio.RECHAZADA)

    def test_admin_puede_aprobar(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {
            "estado": SolicitudCambio.APROBADA,
            "respuesta": "Aprobado",
        })
        self.assertRedirects(response, reverse("lista_solicitudes"))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, SolicitudCambio.APROBADA)

    def test_solicitud_ya_respondida_redirige_con_warning(self):
        self.solicitud.estado = SolicitudCambio.APROBADA
        self.solicitud.save(validate=False)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("lista_solicitudes"))