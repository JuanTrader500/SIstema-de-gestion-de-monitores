"""
tests_modelo_form.py — app asignaciones (complemento al tests.py existente)

El tests.py de asignaciones ya cubre el service crear_asignaciones.
Este archivo agrega cobertura sobre:
  - Modelo Asignacion.clean() (rol del monitor, conflicto de horario)
  - Constraints UniqueConstraint (horario+semestre, monitor+horario+semestre)
  - Form CrearAsignacionesForm (clean_horarios, clean general)
"""

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from asignaciones.forms import CrearAsignacionesForm
from asignaciones.models import Asignacion
from horarios.models import Horario
from salas.models import Sala
from semestres.models import Semestre
from usuarios.models import Usuario
from django.db import IntegrityError
from django.core.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usuario(email, cedula, rol=Usuario.MONITOR) -> Usuario:
    return Usuario.objects.create_user(
        username=email, email=email, password="pass",
        cedula=cedula, rol=rol, first_name="N", last_name="A",
    )


def _sala(codigo="S-101") -> Sala:
    return Sala.objects.create(codigo=codigo, nombre="Lab", capacidad=20)


def _semestre() -> Semestre:
    return Semestre.objects.create(anio=2026, periodo=1, activo=True)


def _horario(sala, dia=1, inicio=time(8, 0), fin=time(10, 0)) -> Horario:
    return Horario.objects.create(
        sala=sala, dia_semana=dia, hora_inicio=inicio, hora_fin=fin,
    )


# ===========================================================================
# 1. Modelo Asignacion — clean()
# ===========================================================================

    class AsignacionCleanTests(TestCase):

        def setUp(self):
            self.sala = _sala()
            self.semestre = _semestre()
            self.monitor = _usuario("m@u.edu", "001")
            self.admin = _usuario("a@u.edu", "999", rol=Usuario.ADMIN)
            self.horario = _horario(self.sala)

        def test_monitor_valido_no_lanza_error(self):
            a = Asignacion(monitor=self.monitor, horario=self.horario, semestre=self.semestre)
            try:
                a.clean()
            except ValidationError:
                self.fail("clean() lanzó error con datos válidos.")

        def test_admin_como_monitor_falla(self):
            a = Asignacion(monitor=self.admin, horario=self.horario, semestre=self.semestre)
            with self.assertRaises(ValidationError) as ctx:
                a.clean()
            self.assertIn("monitor", ctx.exception.message_dict)

        def test_conflicto_de_horario_mismo_monitor_mismo_semestre_falla(self):
            sala_a = Sala.objects.create(codigo="S-A", nombre="Sala A", capacidad=10)
            sala_b = Sala.objects.create(codigo="S-B", nombre="Sala B", capacidad=10)

            horario1 = _horario(sala_a, dia=1, inicio=time(8, 0), fin=time(10, 0))
            horario2 = _horario(sala_b, dia=1, inicio=time(9, 0), fin=time(11, 0))

            Asignacion.objects.create(
                monitor=self.monitor, horario=horario1, semestre=self.semestre,
            )

            a = Asignacion(monitor=self.monitor, horario=horario2, semestre=self.semestre)  # ✅ indentado
            with self.assertRaises(ValidationError):                                         # ✅ indentado
                a.clean()

        def test_sin_conflicto_distinto_dia_es_valido(self):
            Asignacion.objects.create(
                monitor=self.monitor, horario=self.horario, semestre=self.semestre,
            )
            horario_martes = _horario(self.sala, dia=2, inicio=time(8, 0), fin=time(10, 0))
            a = Asignacion(monitor=self.monitor, horario=horario_martes, semestre=self.semestre)
            try:
                a.clean()
            except ValidationError:
                self.fail("No debe haber conflicto en días distintos.")

        # Intentar asignar horario2 (solapado) al mismo monitor debe fallar
        a = Asignacion(monitor=self.monitor, horario=horario2, semestre=self.semestre)
        with self.assertRaises(ValidationError):
            a.clean()

        def test_sin_conflicto_distinto_dia_es_valido(self):
            Asignacion.objects.create(
                monitor=self.monitor, horario=self.horario, semestre=self.semestre,
            )
            horario_martes = _horario(self.sala, dia=2, inicio=time(8, 0), fin=time(10, 0))
            a = Asignacion(monitor=self.monitor, horario=horario_martes, semestre=self.semestre)
            try:
                a.clean()
            except ValidationError:
                self.fail("No debe haber conflicto en días distintos.")


# ===========================================================================
# 2. Constraints UniqueConstraint
# ===========================================================================

class AsignacionUniqueConstraintTests(TestCase):

    def setUp(self):
        self.sala = _sala()
        self.semestre = _semestre()
        self.monitor1 = _usuario("m1@u.edu", "001")
        self.monitor2 = _usuario("m2@u.edu", "002")
        self.horario = _horario(self.sala)
        # Primera asignación válida
        Asignacion.objects.create(
            monitor=self.monitor1, horario=self.horario, semestre=self.semestre,
        )

    def test_mismo_horario_mismo_semestre_distinto_monitor_falla(self):
        # monitor2 en el mismo horario/semestre → viola uq_asig_horario_semestre
        # clean() no detecta esto (no es conflicto del monitor2 consigo mismo)
        # → llega a BD y lanza IntegrityError
        with self.assertRaises((ValidationError, IntegrityError)):
            Asignacion.objects.create(
                monitor=self.monitor2, horario=self.horario, semestre=self.semestre,
            )

    def test_mismo_monitor_mismo_horario_mismo_semestre_falla(self):
        # monitor1 en el mismo horario/semestre → clean() detecta solapamiento
        # antes de llegar a BD → lanza ValidationError
        with self.assertRaises((ValidationError, IntegrityError)):
            Asignacion.objects.create(
                monitor=self.monitor1, horario=self.horario, semestre=self.semestre,
            )

# ===========================================================================
# 3. Form CrearAsignacionesForm — clean_horarios
# ===========================================================================

class CrearAsignacionesFormHorariosTests(TestCase):

    def setUp(self):
        self.sala = _sala()
        self.semestre = _semestre()
        self.monitor = _usuario("m@u.edu", "001")

    def _form(self, horarios_raw, sala_id=None):
        return CrearAsignacionesForm(
            data={
                "monitor": self.monitor.email,
                "sala_id": sala_id or self.sala.id_sala,
                "semestre": self.semestre.pk,
                "horarios": horarios_raw,
            },
            monitor_queryset=Usuario.objects.filter(rol=Usuario.MONITOR),
            semestre_queryset=Semestre.objects.all(),
        )

    def test_token_h_valido(self):
        h = _horario(self.sala)
        form = self._form(f"h:{h.id_horario}")
        form.is_valid()
        self.assertNotIn("horarios", form.errors)

    def test_token_n_valido(self):
        form = self._form("n:1|08:00|10:00")
        form.is_valid()
        self.assertNotIn("horarios", form.errors)

    def test_token_invalido_lanza_error(self):
        form = self._form("x:invalido")
        self.assertFalse(form.is_valid())

    def test_hora_fin_antes_inicio_en_token_n_falla(self):
        form = self._form("n:1|10:00|08:00")
        self.assertFalse(form.is_valid())

    def test_tokens_duplicados_se_deduplicam(self):
        h = _horario(self.sala)
        form = self._form(f"h:{h.id_horario},h:{h.id_horario}")
        form.is_valid()
        horarios = form.cleaned_data.get("horarios", [])
        self.assertEqual(len(horarios), 1)

    def test_horarios_vacio_falla_en_clean(self):
        form = self._form("")
        self.assertFalse(form.is_valid())

    def test_sala_id_invalido_falla(self):
        form = self._form("n:1|08:00|10:00", sala_id=9999)
        self.assertFalse(form.is_valid())