import json
import logging
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

from .forms import MonitorCreationForm
from .models import Usuario
from AI_implementation.ai_orchestrator import get_ai_response


def role_required(expected_role):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.rol != expected_role:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


admin_required = role_required(Usuario.ADMIN)
monitor_required = role_required(Usuario.MONITOR)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect("post_login_router")
        return render(
            request, "usuarios/login.html", {"error": "Credenciales inválidas."}
        )

    return render(request, "usuarios/login.html")


@login_required
def post_login_router(request):
    if request.user.rol == Usuario.ADMIN:
        return redirect("admin_dashboard")
    if request.user.rol == Usuario.MONITOR:
        return redirect("monitor_dashboard")
    raise PermissionDenied


@admin_required
@require_http_methods(["GET", "POST"])
def crear_monitor_view(request):
    if request.method == "POST":
        form = MonitorCreationForm(request.POST)
        if form.is_valid():
            # Create the monitor with an unusable password (must set via reset link).
            monitor = Usuario.objects.create_user(
                username=form.cleaned_data["email"],
                email=form.cleaned_data["email"],
                cedula=form.cleaned_data["cedula"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                telefono=form.cleaned_data["telefono"],
                rol=Usuario.MONITOR,
                password=None,
            )

            # Generate a one-time password reset link.
            token_generator = PasswordResetTokenGenerator()
            uid = urlsafe_base64_encode(force_bytes(monitor.pk))
            token = token_generator.make_token(monitor)
            reset_path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
            site_url = settings.SITE_URL.rstrip("/")
            reset_url = f"{site_url}{reset_path}"

            # Send welcome email with reset link (no password in plaintext).
            html_message = render_to_string(
                "emails/bienvenida_monitor.html",
                {
                    "first_name": monitor.first_name,
                    "email": monitor.email,
                    "reset_url": reset_url,
                },
            )
            text_message = (
                f"Hola {monitor.first_name},\n\n"
                "Tu cuenta de monitor fue creada.\n"
                f"Usuario: {monitor.email}\n\n"
                "Para establecer tu contraseña, visita el siguiente enlace:\n"
                f"{reset_url}\n\n"
                "El enlace expirará en 1 hora."
            )
            try:
                send_mail(
                    "Bienvenido al SGM SC - Establece tu contraseña",
                    text_message,
                    settings.EMAIL_HOST_USER,
                    [monitor.email],
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception:
                logger.exception("Error enviando correo de activación para %s", monitor.email)
                monitor.delete()
                messages.error(
                    request,
                    "No se pudo enviar el correo de activación. El monitor no fue creado.",
                )
                return render(request, "usuarios/crear_monitor.html", {"form": form})

            messages.success(
                request, "Monitor creado. Se envió el correo con el enlace de activación."
            )
            return redirect("admin_dashboard")
    else:
        form = MonitorCreationForm()

    return render(request, "usuarios/crear_monitor.html", {"form": form})


@admin_required
def admin_dashboard(request):
    context = {
        "admin_username": request.user.username,
    }
    return render(request, "usuarios/admin_dashboard.html", context)


@monitor_required
def monitor_dashboard(request):
    return render(request, "usuarios/monitor_dashboard.html")


class CustomPasswordResetView(auth_views.PasswordResetView):
    """PasswordResetView que usa SITE_DOMAIN/SITE_PROTOCOL de settings
    en lugar de request.get_host() (mitiga Host Header Injection)."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["protocol"] = settings.SITE_PROTOCOL
        context["domain"] = settings.SITE_DOMAIN
        return context

    def form_valid(self, form):
        form.save(
            use_https=settings.SITE_PROTOCOL == "https",
            email_template_name=self.email_template_name,
            subject_template_name=self.subject_template_name,
            request=self.request,
            html_email_template_name=self.html_email_template_name,
            domain_override=settings.SITE_DOMAIN,
            extra_email_context={
                "protocol": settings.SITE_PROTOCOL,
                "domain": settings.SITE_DOMAIN,
            },
        )
        return super(auth_views.PasswordResetView, self).form_valid(form)


@require_http_methods(["POST"])
@csrf_protect
def logout_view(request):
    logout(request)
    return redirect("login")


@admin_required
@require_http_methods(["POST"])
@csrf_protect
def ai_chat_api(request):
    """
    Endpoint API para recibir mensajes y devolver respuestas del bot IA.

    - Solo accesible por admins autenticados (@admin_required)
    - session_id = request.user.username (contexto aislado en BD vectorial)
    - Ejecuta get_ai_response async de forma sincrónica
    """
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()

        if not user_message:
            return JsonResponse({"error": "Mensaje vacío"}, status=400)

        # session_id es el username del admin (contexto crítico)
        session_id = request.user.username

        # Convertir async a sync
        ai_response = async_to_sync(get_ai_response)(
            user_message=user_message, session_id=session_id
        )

        return JsonResponse(
            {
                "success": True,
                "response": ai_response,
                "session_id": session_id,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    except PermissionDenied:
        return JsonResponse({"error": "No tienes permisos"}, status=403)
    except Exception as e:
        logger.exception("Error en ai_chat_api: %s", e)
        return JsonResponse({"error": "Error interno del servidor"}, status=500)
