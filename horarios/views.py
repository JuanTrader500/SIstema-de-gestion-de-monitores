from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from usuarios.views import admin_required

from .forms import HorarioForm
from .models import Horario
from .services import actualizar_horario, crear_horario, eliminar_horario


@admin_required
def listar_horarios(request):
    horarios = Horario.objects.select_related("sala").all()
    if request.htmx and request.htmx.target:
        return render(request, "partials/_tabla_horarios.html", {"horarios": horarios})
    return render(request, "horarios/listar.html", {"horarios": horarios})


@admin_required
@require_http_methods(["GET", "POST"])
def crear_horario(request):
    if request.method == "POST":
        form = HorarioForm(data=request.POST)
        if form.is_valid():
            crear_horario(
                sala_id=form.cleaned_data["sala"].id_sala,
                dia_semana=int(form.cleaned_data["dia_semana"]),
                hora_inicio=form.cleaned_data["hora_inicio"],
                hora_fin=form.cleaned_data["hora_fin"],
            )
            response = HttpResponse()
            response["HX-Trigger"] = (
                '{"show-toast":{"type":"success","message":"Horario creado correctamente."}}'
            )
            response["HX-Location"] = reverse("horarios:listar")
            return response
        return render(request, "partials/_form_horario.html", {"form": form})
    form = HorarioForm()
    return render(request, "partials/_form_horario.html", {"form": form})


@admin_required
@require_http_methods(["GET", "POST"])
def editar_horario(request, id_horario):
    horario = get_object_or_404(Horario, pk=id_horario)
    if request.method == "POST":
        form = HorarioForm(data=request.POST, horario_id=id_horario)
        if form.is_valid():
            actualizar_horario(
                id_horario=id_horario,
                sala_id=form.cleaned_data["sala"].id_sala,
                dia_semana=int(form.cleaned_data["dia_semana"]),
                hora_inicio=form.cleaned_data["hora_inicio"],
                hora_fin=form.cleaned_data["hora_fin"],
            )
            response = HttpResponse()
            response["HX-Trigger"] = (
                '{"show-toast":{"type":"success","message":"Horario actualizado correctamente."}}'
            )
            response["HX-Location"] = reverse("horarios:listar")
            return response
        return render(request, "partials/_form_horario.html", {"form": form})
    form = HorarioForm(
        initial={
            "sala": horario.sala_id,
            "dia_semana": str(horario.dia_semana),
            "hora_inicio": horario.hora_inicio,
            "hora_fin": horario.hora_fin,
        },
        horario_id=id_horario,
    )
    return render(request, "partials/_form_horario.html", {"form": form})


@admin_required
@require_http_methods(["POST"])
def eliminar_horario(request, id_horario):
    get_object_or_404(Horario, pk=id_horario)
    eliminar_horario(id_horario=id_horario)
    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse("horarios:listar")
    response["HX-Trigger"] = (
        '{"show-toast":{"type":"success","message":"Horario eliminado correctamente."}}'
    )
    return response
