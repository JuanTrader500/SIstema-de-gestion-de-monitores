"""
tests.py — app cambios

Cubre:
  - Modelo SolicitudCambio (clean: dueño, mismo solicitante/reemplazo,
    rol reemplazo, conflicto horario, una sola pendiente por asignación,
    motivo obligatorio con mín. 10 caracteres, evidencia obligatoria en PDF/imagen)
  - save() actualiza fecha_respuesta al cambiar estado
  - Service crear_solicitud_cambio
  - Service aprobar_solicitud (cambia monitor de asignación, verifica conflicto, divide bloques)
  - Service rechazar_solicitud
  - Vista crear_solicitud_view (grilla semanal, selección de bloques, evidencia obligatoria, nombres)
  - Vista mis_solicitudes_view (solo ve las propias)
  - Vista lista_solicitudes_view (solo admin)
  - Vista responder_solicitud_view (aprueba/rechaza)
"""

from datetime import time

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
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
        cedula=cedula, rol=rol, first_name="Nombre", last_name="Apellido",
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


def _dummy_pdf(nombre="comprobante.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(nombre, b"%PDF-1.4 prueba", content_type="application/pdf")


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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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
            motivo="Primera solicitud justificada",
            evidencia=_dummy_pdf(),
        )
        # Segunda intenta crearse con validate=False para llegar al clean
        s = self._solicitud_base(motivo="Segunda solicitud justificada")
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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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
            motivo="No puedo ir por calamidad doméstica",
            evidencia=_dummy_pdf(),
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
                motivo="Motivo justificado de más de diez caracteres",
                evidencia=_dummy_pdf(),
            )

    def test_falla_si_reemplazo_igual_solicitante(self):
        with self.assertRaises(ValidationError):
            services.crear_solicitud_cambio(
                asignacion=self.asignacion,
                solicitante=self.monitor1,
                monitor_reemplazo=self.monitor1,
                motivo="Motivo justificado de más de diez caracteres",
                evidencia=_dummy_pdf(),
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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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
            "motivo": "No puedo asistir por cita médica",
            "evidencia": _dummy_pdf(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SolicitudCambio.objects.count(), 1)

    def test_post_invalido_no_crea_solicitud(self):
        self.client.force_login(self.monitor1)
        response = self.client.post(self.url, {
            "asignacion": self.asignacion.pk,
            "monitor_reemplazo": self.monitor1.pk,  # mismo que solicitante
            "motivo": "Motivo justificado de más de diez caracteres",
            "evidencia": _dummy_pdf(),
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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
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


# ===========================================================================
# 7. Pruebas de Motivo Obligatorio y Evidencia Obligatoria
# ===========================================================================

class SolicitudMotivoYEvidenciaTests(BaseTestCase):
    """Pruebas para validaciones de motivo y evidencia adjunta obligatoria."""

    def test_motivo_vacio_falla_clean(self):
        s = SolicitudCambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo="",
            evidencia=_dummy_pdf(),
        )
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("motivo", ctx.exception.message_dict)

    def test_motivo_menor_a_10_caracteres_falla_clean(self):
        s = SolicitudCambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo="Corto",
            evidencia=_dummy_pdf(),
        )
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("motivo", ctx.exception.message_dict)

    def test_motivo_valido_pasa_clean(self):
        s = SolicitudCambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo="Tengo cita médica odontológica inaplazable.",
            evidencia=_dummy_pdf(),
        )
        try:
            s.clean()
        except ValidationError:
            self.fail("clean() falló con un motivo válido de más de 10 caracteres.")

    def test_evidencia_obligatoria_falla_si_no_se_adjunta(self):
        s = SolicitudCambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("evidencia", ctx.exception.message_dict)

    def test_evidencia_formato_no_permitido_falla(self):
        archivo_invalido = SimpleUploadedFile("virus.exe", b"binary...", content_type="application/octet-stream")
        s = SolicitudCambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=archivo_invalido,
        )
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("evidencia", ctx.exception.message_dict)

    def test_evidencia_mayor_a_10mb_falla(self):
        contenido_pesado = b"0" * (11 * 1024 * 1024)
        archivo_pesado = SimpleUploadedFile("pesado.pdf", contenido_pesado, content_type="application/pdf")
        s = SolicitudCambio(
            asignacion=self.asignacion,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=archivo_pesado,
        )
        with self.assertRaises(ValidationError) as ctx:
            s.clean()
        self.assertIn("evidencia", ctx.exception.message_dict)


# ===========================================================================
# 8. Pruebas de Reemplazo por Bloques de 1 Hora y Grilla
# ===========================================================================

class ReemplazoPorBloquesTests(BaseTestCase):
    """Pruebas para la funcionalidad de reemplazo fraccionado (bloques de 1 hora)."""

    def setUp(self):
        super().setUp()
        self.sala_lab = _sala("LAB-404")
        self.horario_4h = _horario(self.sala_lab, dia=2, inicio=time(7, 0), fin=time(11, 0))
        self.asignacion_4h = _asignacion(self.monitor1, self.horario_4h, self.semestre)

    def test_solicitud_bloque_1_hora_valida(self):
        solicitud = SolicitudCambio(
            asignacion=self.asignacion_4h,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            hora_inicio_reemplazo=time(8, 0),
            hora_fin_reemplazo=time(9, 0),
            motivo="Cita médica de 8 a 9 de la mañana",
            evidencia=_dummy_pdf(),
        )
        solicitud.clean()
        self.assertTrue(solicitud.es_reemplazo_parcial)
        self.assertEqual(solicitud.duracion_reemplazo_horas, 1)
        self.assertEqual(solicitud.duracion_titular_horas, 3)

    def test_solicitud_bloque_multiples_horas_hasta_n_menos_1(self):
        solicitud = SolicitudCambio(
            asignacion=self.asignacion_4h,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            hora_inicio_reemplazo=time(8, 0),
            hora_fin_reemplazo=time(11, 0),
            motivo="Tengo compromiso académico en la mañana",
            evidencia=_dummy_pdf(),
        )
        solicitud.clean()
        self.assertTrue(solicitud.es_reemplazo_parcial)
        self.assertEqual(solicitud.duracion_reemplazo_horas, 3)
        self.assertEqual(solicitud.duracion_titular_horas, 1)

    def test_bloque_fuera_del_horario_asignado_falla(self):
        solicitud = SolicitudCambio(
            asignacion=self.asignacion_4h,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            hora_inicio_reemplazo=time(6, 0),
            hora_fin_reemplazo=time(7, 0),
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
        )
        with self.assertRaises(ValidationError) as ctx:
            solicitud.clean()
        self.assertIn("hora_inicio_reemplazo", ctx.exception.message_dict)

    def test_bloque_con_hora_fin_menor_que_inicio_falla(self):
        solicitud = SolicitudCambio(
            asignacion=self.asignacion_4h,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            hora_inicio_reemplazo=time(9, 0),
            hora_fin_reemplazo=time(8, 0),
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
        )
        with self.assertRaises(ValidationError) as ctx:
            solicitud.clean()
        self.assertIn("hora_fin_reemplazo", ctx.exception.message_dict)

    def test_reemplazo_disponible_en_bloque_pero_ocupado_en_otro_no_falla(self):
        sala_otra = _sala("SAL-999")
        h_otro = _horario(sala_otra, dia=2, inicio=time(9, 0), fin=time(11, 0))
        _asignacion(self.monitor2, h_otro, self.semestre)

        solicitud = SolicitudCambio(
            asignacion=self.asignacion_4h,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            hora_inicio_reemplazo=time(7, 0),
            hora_fin_reemplazo=time(8, 0),
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
        )
        try:
            solicitud.clean()
        except ValidationError:
            self.fail("clean() falló aunque el monitor de reemplazo está libre en ese bloque específico.")

    def test_reemplazo_con_conflicto_en_el_bloque_especifico_falla(self):
        sala_otra = _sala("SAL-998")
        h_otro = _horario(sala_otra, dia=2, inicio=time(7, 0), fin=time(8, 0))
        _asignacion(self.monitor2, h_otro, self.semestre)

        solicitud = SolicitudCambio(
            asignacion=self.asignacion_4h,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            tipo=SolicitudCambio.TIPO_CAMBIO_TURNO,
            hora_inicio_reemplazo=time(7, 0),
            hora_fin_reemplazo=time(8, 0),
            motivo="Motivo justificado de más de diez caracteres",
            evidencia=_dummy_pdf(),
        )
        with self.assertRaises(ValidationError) as ctx:
            solicitud.clean()
        self.assertIn("monitor_reemplazo", ctx.exception.message_dict)

    def test_aprobar_reemplazo_parcial_en_el_medio_divide_correctamente(self):
        solicitud = services.crear_solicitud_cambio(
            asignacion=self.asignacion_4h,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            hora_inicio_reemplazo=time(8, 0),
            hora_fin_reemplazo=time(9, 0),
            motivo="Cita médica inaplazable en la mañana",
            evidencia=_dummy_pdf(),
        )
        services.aprobar_solicitud(solicitud=solicitud, admin=self.admin)

        asigs_m2 = Asignacion.objects.filter(monitor=self.monitor2, semestre=self.semestre)
        self.assertEqual(asigs_m2.count(), 1)
        self.assertEqual(asigs_m2.first().horario.hora_inicio, time(8, 0))
        self.assertEqual(asigs_m2.first().horario.hora_fin, time(9, 0))

        asigs_m1 = Asignacion.objects.filter(monitor=self.monitor1, semestre=self.semestre, horario__sala=self.sala_lab)
        self.assertEqual(asigs_m1.count(), 2)
        bloques_m1 = sorted([(a.horario.hora_inicio, a.horario.hora_fin) for a in asigs_m1])
        self.assertEqual(bloques_m1, [(time(7, 0), time(8, 0)), (time(9, 0), time(11, 0))])

    def test_aprobar_reemplazo_parcial_al_inicio(self):
        solicitud = services.crear_solicitud_cambio(
            asignacion=self.asignacion_4h,
            solicitante=self.monitor1,
            monitor_reemplazo=self.monitor2,
            hora_inicio_reemplazo=time(7, 0),
            hora_fin_reemplazo=time(8, 0),
            motivo="Compromiso temprano de 7 a 8",
            evidencia=_dummy_pdf(),
        )
        services.aprobar_solicitud(solicitud=solicitud, admin=self.admin)

        asig_m2 = Asignacion.objects.filter(monitor=self.monitor2, semestre=self.semestre).first()
        self.assertEqual(asig_m2.horario.hora_inicio, time(7, 0))
        self.assertEqual(asig_m2.horario.hora_fin, time(8, 0))

        asig_m1 = Asignacion.objects.filter(monitor=self.monitor1, semestre=self.semestre, horario__sala=self.sala_lab).first()
        self.assertEqual(asig_m1.horario.hora_inicio, time(8, 0))
        self.assertEqual(asig_m1.horario.hora_fin, time(11, 0))

    def test_vista_crear_solicitud_muestra_grilla_y_nombres(self):
        client = Client()
        client.force_login(self.monitor1)
        response = client.get(reverse("crear_solicitud"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("grid_rows", response.context)
        self.assertIn("asig_data_json", response.context)

        form = response.context["form"]
        label_reemplazo = form.fields["monitor_reemplazo"].label_from_instance(self.monitor2)
        self.assertEqual(label_reemplazo, self.monitor2.get_full_name())
        self.assertNotIn("@", label_reemplazo)
