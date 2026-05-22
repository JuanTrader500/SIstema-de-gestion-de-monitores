from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from usuarios.views import admin_required

from .forms import SemestreForm
from .models import Semestre
from .services import actualizar_semestre, crear_semestre, eliminar_semestre


@admin_required
def listar_semestres(request):
    semestres = Semestre.objects.all()
    if request.htmx and request.htmx.target:
        return render(request, "partials/_tabla_semestres.html", {"semestres": semestres})
    return render(request, "semestres/listar.html", {"semestres": semestres})


@admin_required
@require_http_methods(["GET", "POST"])
def crear_semestre(request):
    if request.method == "POST":
        form = SemestreForm(data=request.POST)
        if form.is_valid():
            crear_semestre(
                anio=form.cleaned_data["anio"],
                periodo=int(form.cleaned_data["periodo"]),
                activo=form.cleaned_data.get("activo", False),
            )
            response = HttpResponse()
            response["HX-Trigger"] = (
                '{"show-toast":{"type":"success","message":"Semestre creado correctamente."}}'
            )
            response["HX-Location"] = reverse("semestres:listar")
            return response
        return render(request, "partials/_form_semestre.html", {"form": form})
    form = SemestreForm()
    return render(request, "partials/_form_semestre.html", {"form": form})


@admin_required
@require_http_methods(["GET", "POST"])
def editar_semestre(request, id_semestre):
    semestre = get_object_or_404(Semestre, pk=id_semestre)
    if request.method == "POST":
        form = SemestreForm(data=request.POST, semestre_id=id_semestre)
        if form.is_valid():
            actualizar_semestre(
                id_semestre=id_semestre,
                anio=form.cleaned_data["anio"],
                periodo=int(form.cleaned_data["periodo"]),
                activo=form.cleaned_data.get("activo", False),
            )
            response = HttpResponse()
            response["HX-Trigger"] = (
                '{"show-toast":{"type":"success","message":"Semestre actualizado correctamente."}}'
            )
            response["HX-Location"] = reverse("semestres:listar")
            return response
        return render(request, "partials/_form_semestre.html", {"form": form})
    form = SemestreForm(
        initial={
            "anio": semestre.anio,
            "periodo": str(semestre.periodo),
            "activo": semestre.activo,
        },
        semestre_id=id_semestre,
    )
    return render(request, "partials/_form_semestre.html", {"form": form})


@admin_required
@require_http_methods(["POST"])
def eliminar_semestre(request, id_semestre):
    get_object_or_404(Semestre, pk=id_semestre)
    eliminar_semestre(id_semestre=id_semestre)
    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse("semestres:listar")
    response["HX-Trigger"] = (
        '{"show-toast":{"type":"success","message":"Semestre eliminado correctamente."}}'
    )
    return response
