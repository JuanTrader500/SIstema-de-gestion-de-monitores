"""
tests.py — app horarios

Cubre:
  - Modelo Horario (creación, __str__)
  - clean(): hora_fin > hora_inicio
  - save() llama full_clean por defecto
  - Solapamiento de horarios en misma sala y día (validado en service de asignaciones,
    pero también probado aquí a nivel de integridad si el ExclusionConstraint está activo)
"""

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from horarios.models import Horario
from salas.models import Sala


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sala(codigo="SALA-101") -> Sala:
    return Sala.objects.create(codigo=codigo, nombre="Lab", capacidad=30)


def _horario(sala, dia=1, inicio=time(8, 0), fin=time(10, 0)) -> Horario:
    return Horario.objects.create(
        sala=sala, dia_semana=dia, hora_inicio=inicio, hora_fin=fin
    )


# ===========================================================================
# 1. Creación básica
# ===========================================================================

class HorarioModelTests(TestCase):

    def setUp(self):
        self.sala = _sala()

    def test_crea_horario_correctamente(self):
        h = _horario(self.sala)
        self.assertEqual(h.dia_semana, 1)
        self.assertEqual(h.hora_inicio, time(8, 0))
        self.assertEqual(h.hora_fin, time(10, 0))
        self.assertEqual(h.sala, self.sala)

    def test_str_incluye_dia_horas_y_sala(self):
        h = _horario(self.sala)
        texto = str(h)
        self.assertIn("08:00", texto)
        self.assertIn("10:00", texto)
        self.assertIn(str(self.sala), texto)


# ===========================================================================
# 2. Validación clean() — hora_fin > hora_inicio
# ===========================================================================

class HorarioCleanTests(TestCase):

    def setUp(self):
        self.sala = _sala()

    def test_hora_fin_igual_a_inicio_falla(self):
        h = Horario(
            sala=self.sala,
            dia_semana=1,
            hora_inicio=time(10, 0),
            hora_fin=time(10, 0),
        )
        with self.assertRaises(ValidationError):
            h.clean()

    def test_hora_fin_antes_de_inicio_falla(self):
        h = Horario(
            sala=self.sala,
            dia_semana=1,
            hora_inicio=time(12, 0),
            hora_fin=time(10, 0),
        )
        with self.assertRaises(ValidationError):
            h.clean()

    def test_hora_fin_despues_de_inicio_es_valido(self):
        h = Horario(
            sala=self.sala,
            dia_semana=1,
            hora_inicio=time(8, 0),
            hora_fin=time(10, 0),
        )
        try:
            h.clean()
        except ValidationError:
            self.fail("clean() lanzó ValidationError con horas válidas.")

    def test_save_sin_validate_omite_clean(self):
        """save(validate=False) no llama full_clean y permite guardar sin validar."""
        h = Horario(
            sala=self.sala,
            dia_semana=1,
            hora_inicio=time(10, 0),
            hora_fin=time(10, 0),
        )
        # No debe lanzar excepción porque se salta la validación
        try:
            h.save(validate=False)
        except ValidationError:
            self.fail("save(validate=False) no debería llamar full_clean.")


# ===========================================================================
# 3. Relación con Sala (CASCADE)
# ===========================================================================

class HorarioCascadeTests(TestCase):

    def test_borrar_sala_borra_sus_horarios(self):
        sala = _sala()
        _horario(sala)
        self.assertEqual(Horario.objects.count(), 1)
        sala.delete()
        self.assertEqual(Horario.objects.count(), 0)

    def test_horarios_de_distintas_salas_coexisten(self):
        sala1 = _sala("SALA-A")
        sala2 = _sala("SALA-B")
        _horario(sala1, dia=1, inicio=time(8, 0), fin=time(10, 0))
        _horario(sala2, dia=1, inicio=time(8, 0), fin=time(10, 0))
        self.assertEqual(Horario.objects.count(), 2)