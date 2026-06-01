import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from usuarios.views import admin_required

from .forms import SalaForm
from .models import Sala
from .services import actualizar_sala
from .services import crear_sala as service_crear_sala
from .services import eliminar_sala as service_eliminar_sala


@admin_required
def listar_salas(request):
    salas = Sala.objects.all()
    if request.htmx and request.htmx.target:
        return render(request, "partials/_tabla_salas.html", {"salas": salas})
    return render(request, "salas/listar.html", {"salas": salas})


@admin_required
@require_http_methods(["GET", "POST"])
def crear_sala(request):
    if request.method == "POST":
        form = SalaForm(data=request.POST)
        if form.is_valid():
            try:
                service_crear_sala(
                    codigo=form.cleaned_data["codigo"],
                    nombre=form.cleaned_data["nombre"],
                    capacidad=form.cleaned_data["capacidad"],
                )
            except ValidationError as e:
                form.add_error(None, str(e))
                return render(request, "partials/_form_sala.html", {"form": form})
            messages.success(request, "Sala creada correctamente.")
            response = HttpResponse()
            response["HX-Redirect"] = reverse("salas:listar")
            return response
        return render(request, "partials/_form_sala.html", {"form": form})
    form = SalaForm()
    return render(request, "partials/_form_sala.html", {"form": form})


@admin_required
@require_http_methods(["GET", "POST"])
def editar_sala(request, id_sala):
    sala = get_object_or_404(Sala, pk=id_sala)
    if request.method == "POST":
        form = SalaForm(data=request.POST, sala_id=id_sala)
        if form.is_valid():
            try:
                actualizar_sala(
                    id_sala=id_sala,
                    codigo=form.cleaned_data["codigo"],
                    nombre=form.cleaned_data["nombre"],
                    capacidad=form.cleaned_data["capacidad"],
                )
            except ValidationError as e:
                form.add_error(None, str(e))
                return render(request, "partials/_form_sala.html", {"form": form})
            messages.success(request, "Sala actualizada correctamente.")
            response = HttpResponse()
            response["HX-Redirect"] = reverse("salas:listar")
            return response
        return render(request, "partials/_form_sala.html", {"form": form})
    form = SalaForm(
        initial={
            "codigo": sala.codigo,
            "nombre": sala.nombre,
            "capacidad": sala.capacidad,
        },
        sala_id=id_sala,
    )
    return render(request, "partials/_form_sala.html", {"form": form})


@admin_required
@require_http_methods(["POST"])
def eliminar_sala(request, id_sala):
    get_object_or_404(Sala, pk=id_sala)
    try:
        service_eliminar_sala(id_sala=id_sala)
    except ValidationError as e:
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({
            "show-toast": {"type": "error", "message": str(e)}
        })
        return response
    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse("salas:listar")
    response["HX-Trigger"] = (
        '{"show-toast":{"type":"success","message":"Sala eliminada correctamente."}}'
    )
    return response
