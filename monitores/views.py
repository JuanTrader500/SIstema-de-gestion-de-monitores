import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from usuarios.models import Usuario
from usuarios.views import admin_required

from .forms import MonitorForm
from .services import actualizar_monitor
from .services import crear_monitor as service_crear_monitor
from .services import eliminar_monitor as service_eliminar_monitor


@admin_required
def listar_monitores(request):
    monitores = Usuario.objects.filter(rol=Usuario.MONITOR).order_by("email")
    if request.htmx and request.htmx.target:
        return render(request, "partials/_tabla_monitores.html", {"monitores": monitores})
    return render(request, "monitores/listar.html", {"monitores": monitores})


@admin_required
@require_http_methods(["GET", "POST"])
def crear_monitor(request):
    if request.method == "POST":
        form = MonitorForm(data=request.POST)
        if form.is_valid():
            try:
                service_crear_monitor(
                    email=form.cleaned_data["email"],
                    cedula=form.cleaned_data["cedula"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    telefono=form.cleaned_data.get("telefono", ""),
                )
            except ValidationError as e:
                form.add_error(None, str(e))
                return render(request, "partials/_form_monitor.html", {"form": form})
            messages.success(request, "Monitor creado correctamente. Se enviaron las credenciales por correo.")
            response = HttpResponse()
            response["HX-Redirect"] = reverse("monitores:listar")
            return response
        return render(request, "partials/_form_monitor.html", {"form": form})
    form = MonitorForm()
    return render(request, "partials/_form_monitor.html", {"form": form})


@admin_required
@require_http_methods(["GET", "POST"])
def editar_monitor(request, id_monitor):
    monitor = get_object_or_404(Usuario, pk=id_monitor, rol=Usuario.MONITOR)
    if request.method == "POST":
        form = MonitorForm(data=request.POST, monitor_id=id_monitor)
        if form.is_valid():
            try:
                actualizar_monitor(
                    id_monitor=id_monitor,
                    email=form.cleaned_data["email"],
                    cedula=form.cleaned_data["cedula"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    telefono=form.cleaned_data.get("telefono", ""),
                )
            except ValidationError as e:
                form.add_error(None, str(e))
                return render(request, "partials/_form_monitor.html", {"form": form})
            messages.success(request, "Monitor actualizado correctamente.")
            response = HttpResponse()
            response["HX-Redirect"] = reverse("monitores:listar")
            return response
        return render(request, "partials/_form_monitor.html", {"form": form})
    form = MonitorForm(
        initial={
            "first_name": monitor.first_name,
            "last_name": monitor.last_name,
            "cedula": monitor.cedula,
            "email": monitor.email,
            "telefono": monitor.telefono,
        },
        monitor_id=id_monitor,
    )
    return render(request, "partials/_form_monitor.html", {"form": form})


@admin_required
@require_http_methods(["POST"])
def eliminar_monitor(request, id_monitor):
    get_object_or_404(Usuario, pk=id_monitor, rol=Usuario.MONITOR)
    try:
        service_eliminar_monitor(id_monitor=id_monitor)
    except ValidationError as e:
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({
            "show-toast": {"type": "error", "message": str(e)}
        })
        return response
    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse("monitores:listar")
    response["HX-Trigger"] = (
        '{"show-toast":{"type":"success","message":"Monitor eliminado correctamente."}}'
    )
    return response
