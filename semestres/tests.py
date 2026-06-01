"""
tests.py — app semestres

Cubre:
  - Modelo Semestre (creación, unicidad anio+periodo, constraint periodo in [1,2])
  - Comportamiento del campo activo
  - __str__
"""

from django.db import IntegrityError
from django.test import TestCase

from semestres.models import Semestre


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _semestre(anio=2026, periodo=1, activo=True) -> Semestre:
    return Semestre.objects.create(anio=anio, periodo=periodo, activo=activo)


# ===========================================================================
# 1. Creación básica
# ===========================================================================

class SemestreModelTests(TestCase):

    def test_crea_semestre_correctamente(self):
        s = _semestre()
        self.assertEqual(s.anio, 2026)
        self.assertEqual(s.periodo, 1)
        self.assertTrue(s.activo)

    def test_str_incluye_anio_y_periodo(self):
        s = _semestre(anio=2025, periodo=2)
        self.assertIn("2025", str(s))
        self.assertIn("2", str(s))

    def test_activo_default_es_false(self):
        s = Semestre.objects.create(anio=2024, periodo=1)
        self.assertFalse(s.activo)


# ===========================================================================
# 2. Unicidad anio + periodo
# ===========================================================================

class SemestreUnicidadTests(TestCase):

    def test_no_permite_duplicado_anio_periodo(self):
        _semestre(anio=2026, periodo=1)
        with self.assertRaises(IntegrityError):
            Semestre.objects.create(anio=2026, periodo=1, activo=False)

    def test_permite_mismo_anio_distinto_periodo(self):
        _semestre(anio=2026, periodo=1)
        s2 = _semestre(anio=2026, periodo=2)
        self.assertEqual(s2.periodo, 2)

    def test_permite_mismo_periodo_distinto_anio(self):
        _semestre(anio=2025, periodo=1)
        s2 = _semestre(anio=2026, periodo=1)
        self.assertEqual(s2.anio, 2026)


# ===========================================================================
# 3. Constraint periodo in [1, 2]
# ===========================================================================

class SemestrePeriodoConstraintTests(TestCase):

    def test_periodo_1_es_valido(self):
        s = _semestre(periodo=1)
        self.assertEqual(s.periodo, 1)

    def test_periodo_2_es_valido(self):
        s = _semestre(anio=2025, periodo=2)
        self.assertEqual(s.periodo, 2)

    def test_periodo_invalido_viola_constraint_bd(self):
        """El CheckConstraint de BD rechaza periodo fuera de [1,2]."""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Semestre.objects.create(anio=2026, periodo=3, activo=False)


# ===========================================================================
# 4. Ordering
# ===========================================================================

class SemestreOrderingTests(TestCase):

    def test_ordering_descendente_por_anio_periodo(self):
        Semestre.objects.create(anio=2024, periodo=1)
        Semestre.objects.create(anio=2026, periodo=1)
        Semestre.objects.create(anio=2025, periodo=2)

        semestres = list(Semestre.objects.all())
        self.assertEqual(semestres[0].anio, 2026)
        self.assertEqual(semestres[-1].anio, 2024)