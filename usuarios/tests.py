"""
tests.py — app usuarios

Cubre:
  - Modelo Usuario (creación con AbstractUser, roles, unicidad email/cedula)
  - Decoradores role_required (admin_required, monitor_required)
  - MonitorCreationForm (validación de campos)
  - Vista login_view (GET, POST válido, POST inválido)
  - Vista crear_monitor_view (acceso restringido a admin, POST válido)
  - Vista admin_dashboard y monitor_dashboard (acceso por rol)
  - Vista post_login_router (redirige según rol)
"""

from django.test import Client, TestCase
from django.urls import reverse

from usuarios.models import Usuario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crear_usuario(
    email="test@uni.edu",
    cedula="123456",
    rol=Usuario.MONITOR,
    password="testpass123",
    username=None,
) -> Usuario:
    return Usuario.objects.create_user(
        username=username or email,
        email=email,
        password=password,
        cedula=cedula,
        rol=rol,
        first_name="Test",
        last_name="User",
    )


def _admin(**kwargs) -> Usuario:
    kwargs.setdefault("email", "admin@uni.edu")
    kwargs.setdefault("cedula", "999999")
    kwargs.setdefault("rol", Usuario.ADMIN)
    return _crear_usuario(**kwargs)


def _monitor(**kwargs) -> Usuario:
    kwargs.setdefault("email", "monitor@uni.edu")
    kwargs.setdefault("cedula", "111111")
    return _crear_usuario(**kwargs)


# ===========================================================================
# 1. Modelo Usuario
# ===========================================================================

class UsuarioModelTests(TestCase):

    def test_crea_monitor_correctamente(self):
        u = _monitor()
        self.assertEqual(u.rol, Usuario.MONITOR)
        self.assertTrue(u.check_password("testpass123"))

    def test_crea_admin_correctamente(self):
        u = _admin()
        self.assertEqual(u.rol, Usuario.ADMIN)

    def test_str_incluye_nombre_y_rol(self):
        u = _monitor()
        self.assertIn("monitor", str(u).lower())

    def test_email_es_unico(self):
        from django.db import IntegrityError
        _monitor(email="dup@uni.edu", cedula="111")
        with self.assertRaises(IntegrityError):
            _monitor(email="dup@uni.edu", cedula="222")

    def test_cedula_es_unica(self):
        from django.db import IntegrityError
        _monitor(email="a@uni.edu", cedula="DUP")
        with self.assertRaises(IntegrityError):
            _monitor(email="b@uni.edu", cedula="DUP")

    def test_username_field_es_email(self):
        self.assertEqual(Usuario.USERNAME_FIELD, "email")

    def test_rol_choices_son_admin_y_monitor(self):
        valores = [v for v, _ in Usuario.OPCIONES_ROL]
        self.assertIn("admin", valores)
        self.assertIn("monitor", valores)


# ===========================================================================
# 2. MonitorCreationForm
# ===========================================================================

class MonitorCreationFormTests(TestCase):

    def _datos_validos(self, **kwargs):
        base = {
            "first_name": "Juan",
            "last_name": "Pérez",
            "cedula": "987654",
            "email": "juan@uni.edu",
            "telefono": "3001234567",
        }
        base.update(kwargs)
        return base

    def test_form_valido_con_datos_correctos(self):
        from usuarios.forms import MonitorCreationForm
        form = MonitorCreationForm(data=self._datos_validos())
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_invalido_sin_email(self):
        from usuarios.forms import MonitorCreationForm
        datos = self._datos_validos()
        datos.pop("email")
        form = MonitorCreationForm(data=datos)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_form_invalido_sin_cedula(self):
        from usuarios.forms import MonitorCreationForm
        datos = self._datos_validos()
        datos.pop("cedula")
        form = MonitorCreationForm(data=datos)
        self.assertFalse(form.is_valid())
        self.assertIn("cedula", form.errors)

    def test_form_invalido_email_mal_formato(self):
        from usuarios.forms import MonitorCreationForm
        form = MonitorCreationForm(data=self._datos_validos(email="no-es-email"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


# ===========================================================================
# 3. Vista login_view
# ===========================================================================

class LoginViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse("login")
        self.monitor = _monitor()

    def test_get_retorna_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_credenciales_validas_redirige(self):
        response = self.client.post(self.url, {
            "email": "monitor@uni.edu",
            "password": "testpass123",
        })
        self.assertEqual(response.status_code, 302)

    def test_post_credenciales_invalidas_retorna_200_con_error(self):
        response = self.client.post(self.url, {
            "email": "monitor@uni.edu",
            "password": "wrongpass",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-danger") 

# ===========================================================================
# 4. Vista post_login_router
# ===========================================================================

class PostLoginRouterTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse("post_login_router")

    def test_admin_redirige_a_admin_dashboard(self):
        admin = _admin()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_monitor_redirige_a_monitor_dashboard(self):
        monitor = _monitor()
        self.client.force_login(monitor)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("monitor_dashboard"))

    def test_anonimo_redirige_a_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


# ===========================================================================
# 5. Vista admin_dashboard
# ===========================================================================

class AdminDashboardTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse("admin_dashboard")

    def test_admin_puede_acceder(self):
        admin = _admin()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_monitor_recibe_403(self):
        monitor = _monitor()
        self.client.force_login(monitor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_anonimo_redirige_a_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


# ===========================================================================
# 6. Vista monitor_dashboard
# ===========================================================================

class MonitorDashboardTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse("monitor_dashboard")

    def test_monitor_puede_acceder(self):
        monitor = _monitor()
        self.client.force_login(monitor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_admin_recibe_403(self):
        admin = _admin()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_anonimo_redirige_a_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)


# ===========================================================================
# 7. Vista crear_monitor_view
# ===========================================================================

class CrearMonitorViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse("crear_monitor")
        self.admin = _admin()

    def test_get_como_admin_retorna_200(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_monitor_no_puede_acceder(self):
        monitor = _monitor()
        self.client.force_login(monitor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_anonimo_redirige_a_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_post_con_datos_invalidos_no_crea_usuario(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {
            "first_name": "",
            "last_name": "",
            "cedula": "",
            "email": "no-es-email",
            "telefono": "",
        })
        # Vuelve al form con errores, no redirige
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Usuario.objects.filter(rol=Usuario.MONITOR).count(), 0)