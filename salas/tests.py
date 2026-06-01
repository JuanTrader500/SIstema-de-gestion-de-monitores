"""
tests.py — app salas

Cubre:
  - Modelo Sala (creación, unicidad de código, __str__)
  - Service: crear_sala, obtener_sala, listar_salas, actualizar_sala, eliminar_sala
  - Vistas JSON: GET /salas/, POST /salas/, GET /salas/<id>/, PATCH /salas/<id>/, DELETE /salas/<id>/
"""

import json

from django.test import Client, TestCase
from django.urls import reverse

from salas.models import Sala
from salas import services


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sala(codigo="SALA-101", nombre="Laboratorio A", capacidad=30) -> Sala:
    return Sala.objects.create(codigo=codigo, nombre=nombre, capacidad=capacidad)


# ===========================================================================
# 1. Modelo
# ===========================================================================

class SalaModelTests(TestCase):

    def test_crea_sala_correctamente(self):
        sala = _sala()
        self.assertEqual(sala.codigo, "SALA-101")
        self.assertEqual(sala.nombre, "Laboratorio A")
        self.assertEqual(sala.capacidad, 30)

    def test_str_incluye_codigo_nombre_capacidad(self):
        sala = _sala()
        self.assertIn("SALA-101", str(sala))
        self.assertIn("Laboratorio A", str(sala))
        self.assertIn("30", str(sala))

    def test_codigo_es_unico(self):
        _sala()
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Sala.objects.create(codigo="SALA-101", nombre="Otra", capacidad=10)

    def test_ordering_por_codigo(self):
        Sala.objects.create(codigo="Z-999", nombre="Z", capacidad=1)
        Sala.objects.create(codigo="A-001", nombre="A", capacidad=1)
        codigos = list(Sala.objects.values_list("codigo", flat=True))
        self.assertEqual(codigos, sorted(codigos))


# ===========================================================================
# 2. Service
# ===========================================================================

class SalaServiceCrearTests(TestCase):

    def test_crear_sala_basica(self):
        sala = services.crear_sala("sala-101", "Lab A", 20)
        self.assertEqual(sala.codigo, "SALA-101")  # normaliza a mayúsculas
        self.assertEqual(sala.capacidad, 20)

    def test_codigo_se_normaliza_a_mayusculas(self):
        sala = services.crear_sala("sala-abc", "Lab", 10)
        self.assertEqual(sala.codigo, "SALA-ABC")

    def test_falla_con_codigo_vacio(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            services.crear_sala("", "Lab", 10)

    def test_falla_con_nombre_vacio(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            services.crear_sala("SALA-X", "", 10)

    def test_falla_con_capacidad_cero(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            services.crear_sala("SALA-X", "Lab", 0)

    def test_falla_con_capacidad_negativa(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            services.crear_sala("SALA-X", "Lab", -5)

    def test_falla_con_capacidad_booleana(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            services.crear_sala("SALA-X", "Lab", True)

    def test_falla_con_codigo_duplicado(self):
        from django.core.exceptions import ValidationError
        services.crear_sala("SALA-101", "Lab A", 10)
        with self.assertRaises(ValidationError):
            services.crear_sala("SALA-101", "Lab B", 20)


class SalaServiceObtenerListarTests(TestCase):

    def setUp(self):
        self.sala = _sala()

    def test_obtener_sala_existente(self):
        sala = services.obtener_sala(self.sala.id_sala)
        self.assertEqual(sala.pk, self.sala.pk)

    def test_obtener_sala_inexistente_lanza_excepcion(self):
        from salas.models import Sala
        with self.assertRaises(Sala.DoesNotExist):
            services.obtener_sala(9999)

    def test_listar_salas_retorna_lista(self):
        resultado = services.listar_salas()
        self.assertIsInstance(resultado, list)
        self.assertEqual(len(resultado), 1)


class SalaServiceActualizarTests(TestCase):

    def setUp(self):
        self.sala = _sala()

    def test_actualizar_nombre(self):
        sala = services.actualizar_sala(self.sala.id_sala, nombre="Nuevo nombre")
        self.assertEqual(sala.nombre, "Nuevo nombre")

    def test_actualizar_capacidad(self):
        sala = services.actualizar_sala(self.sala.id_sala, capacidad=50)
        self.assertEqual(sala.capacidad, 50)

    def test_actualizar_codigo_normaliza_mayusculas(self):
        sala = services.actualizar_sala(self.sala.id_sala, codigo="sala-nueva")
        self.assertEqual(sala.codigo, "SALA-NUEVA")

    def test_falla_actualizar_codigo_duplicado(self):
        from django.core.exceptions import ValidationError
        _sala(codigo="SALA-202")
        with self.assertRaises(ValidationError):
            services.actualizar_sala(self.sala.id_sala, codigo="SALA-202")

    def test_falla_actualizar_capacidad_invalida(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            services.actualizar_sala(self.sala.id_sala, capacidad=0)


class SalaServiceEliminarTests(TestCase):

    def test_eliminar_sala_existente(self):
        sala = _sala()
        services.eliminar_sala(sala.id_sala)
        self.assertFalse(Sala.objects.filter(pk=sala.id_sala).exists())

    def test_eliminar_sala_inexistente_lanza_excepcion(self):
        from salas.models import Sala
        with self.assertRaises(Sala.DoesNotExist):
            services.eliminar_sala(9999)


# ===========================================================================
# 3. Vistas JSON
# ===========================================================================

class SalasVistaListarCrearTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse("salas")

    def test_get_lista_vacia(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["salas"], [])

    def test_get_lista_con_salas(self):
        _sala()
        response = self.client.get(self.url)
        self.assertEqual(len(response.json()["salas"]), 1)

    def test_post_crea_sala(self):
        payload = {"codigo": "SALA-200", "nombre": "Lab B", "capacidad": 25}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["codigo"], "SALA-200")

    def test_post_falla_con_codigo_vacio(self):
        payload = {"codigo": "", "nombre": "Lab", "capacidad": 10}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_post_falla_con_capacidad_invalida(self):
        payload = {"codigo": "SALA-X", "nombre": "Lab", "capacidad": 0}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class SalaVistaDetalleTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.sala = _sala()
        self.url = reverse("sala-detalle", args=[self.sala.id_sala])

    def test_get_sala_existente(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["codigo"], "SALA-101")

    def test_get_sala_inexistente(self):
        url = reverse("sala-detalle", args=[9999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_patch_actualiza_nombre(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"nombre": "Actualizado"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nombre"], "Actualizado")

    def test_patch_falla_con_capacidad_invalida(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"capacidad": -1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_elimina_sala(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Sala.objects.filter(pk=self.sala.id_sala).exists())

    def test_delete_sala_inexistente(self):
        url = reverse("sala-detalle", args=[9999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)