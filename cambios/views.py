import json
from datetime import time
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from usuarios.views import admin_required, monitor_required
from semestres.models import Semestre
from horarios.models import Horario
from .forms import ResponderSolicitudForm, SolicitudCambioForm
from .models import SolicitudCambio
from .services import aprobar_solicitud, rechazar_solicitud


# =========================
# VISTAS PARA MONITORES
# =========================

@monitor_required
@require_http_methods(["GET", "POST"])
def crear_solicitud_view(request):
	"""Vista interactiva para que un monitor cree una solicitud de reemplazo.

	Incluye:
	- Grilla semanal visual de turnos asignados (tipo administrador con cursor interactivo).
	- Selección de reemplazo completo o por bloques de 1 hora (máximo N-1 horas).
	- Subida opcional de evidencia (PDF/Imagen máx 10 MB).
	- Selección de compañero por nombre completo.
	"""
	semestre_activo = Semestre.objects.filter(activo=True).first()

	if request.method == "POST":
		form = SolicitudCambioForm(request.POST, request.FILES, monitor=request.user)
		if form.is_valid():
			try:
				form.save()
				messages.success(request, "Solicitud de reemplazo creada exitosamente.")
				return redirect("mis_solicitudes")
			except ValidationError as exc:
				messages.error(request, str(exc))
	else:
		initial = {}
		asig_id = request.GET.get("asignacion")
		if asig_id:
			initial["asignacion"] = asig_id
		form = SolicitudCambioForm(initial=initial, monitor=request.user)

	# Asignaciones del monitor en el semestre activo
	mis_asignaciones = (
		request.user.asignaciones.filter(semestre=semestre_activo)
		.select_related("horario__sala", "semestre")
		.order_by("horario__dia_semana", "horario__hora_inicio")
		if semestre_activo
		else []
	)

	dias = [
		(1, "Lunes"), (2, "Martes"), (3, "Miércoles"),
		(4, "Jueves"), (5, "Viernes"), (6, "Sábado"),
	]

	# Franjas horarias para construir la grilla semanal
	franjas_qs = Horario.objects.values_list("hora_inicio", "hora_fin").distinct()
	franjas_set = set(franjas_qs)
	if not franjas_set:
		franjas_set = {
			(time(7, 0), time(11, 0)),
			(time(11, 0), time(15, 0)),
			(time(15, 0), time(19, 0)),
			(time(19, 0), time(22, 0)),
		}
	franjas_ordenadas = sorted(list(franjas_set), key=lambda x: (x[0], x[1]))

	# Mapa de asignaciones y datos para interacción en cliente
	asig_map = {}
	asig_data_json = {}
	for a in mis_asignaciones:
		h = a.horario
		asig_map[(h.dia_semana, h.hora_inicio, h.hora_fin)] = a
		# Generar bloques de 1 hora dentro de esta asignación
		bloques = []
		cur_h = h.hora_inicio.hour
		fin_h = h.hora_fin.hour
		for bh in range(cur_h, fin_h):
			ini_str = f"{bh:02d}:00"
			fin_str = f"{bh+1:02d}:00"
			bloques.append({
				"inicio": ini_str,
				"fin": fin_str,
				"label": f"{ini_str} – {fin_str}",
				"hora_num": bh,
			})
		duracion_total = max(1, fin_h - cur_h)
		asig_data_json[str(a.pk)] = {
			"id": a.pk,
			"sala": a.horario.sala.codigo,
			"sala_nombre": a.horario.sala.nombre,
			"dia": a.horario.get_dia_semana_display(),
			"hora_inicio": a.horario.hora_inicio.strftime("%H:%M"),
			"hora_fin": a.horario.hora_fin.strftime("%H:%M"),
			"duracion_horas": duracion_total,
			"bloques": bloques,
		}

	# Filas para la tabla/grilla semanal
	grid_rows = []
	for inicio, fin in franjas_ordenadas:
		label = f"{inicio.strftime('%H:%M')} – {fin.strftime('%H:%M')}"
		cells = []
		for dia_num, _dia_nombre in dias:
			matched_asig = asig_map.get((dia_num, inicio, fin))
			if not matched_asig:
				for a in mis_asignaciones:
					h = a.horario
					if h.dia_semana == dia_num and (h.hora_inicio < fin and h.hora_fin > inicio):
						matched_asig = a
						break
			if matched_asig:
				cells.append({
					"tipo": "mi_turno",
					"asignacion_id": matched_asig.pk,
					"sala": matched_asig.horario.sala.codigo,
					"horario": f"{matched_asig.horario.hora_inicio.strftime('%H:%M')}–{matched_asig.horario.hora_fin.strftime('%H:%M')}",
				})
			else:
				cells.append({
					"tipo": "libre",
				})
		grid_rows.append({"label": label, "cells": cells})

	selected_asignacion_id = request.GET.get("asignacion") or (request.POST.get("asignacion") if request.method == "POST" else "")

	return render(request, "cambios/crear_solicitud.html", {
		"form": form,
		"semestre_activo": semestre_activo,
		"dias": dias,
		"grid_rows": grid_rows,
		"mis_asignaciones": mis_asignaciones,
		"asig_data_json": json.dumps(asig_data_json),
		"selected_asignacion_id": selected_asignacion_id,
	})


@monitor_required
@require_http_methods(["GET"])
def mis_solicitudes_view(request):
	"""Vista para que un monitor vea sus solicitudes de cambio."""
	solicitudes = SolicitudCambio.objects.filter(
		solicitante=request.user
	).select_related(
		"asignacion__horario", "asignacion__semestre", "monitor_reemplazo"
	).order_by("-fecha_creacion")

	return render(request, "cambios/mis_solicitudes.html", {
		"solicitudes": solicitudes,
	})


@monitor_required
@require_http_methods(["GET"])
def mis_asignaciones_view(request):
	"""Vista para que un monitor vea sus asignaciones de turno del semestre activo."""
	semestre_activo = Semestre.objects.filter(activo=True).first()
	asignaciones = request.user.asignaciones.select_related(
		"horario__sala", "semestre"
	)
	if semestre_activo:
		asignaciones = asignaciones.filter(semestre=semestre_activo)
	asignaciones = asignaciones.order_by(
		"horario__dia_semana", "horario__hora_inicio"
	)

	return render(request, "cambios/mis_asignaciones.html", {
		"asignaciones": asignaciones,
		"semestre_activo": semestre_activo,
	})


# =========================
# VISTAS PARA ADMINISTRADORES
# =========================

@admin_required
@require_http_methods(["GET"])
def lista_solicitudes_view(request):
	"""Vista para que el administrador vea todas las solicitudes."""
	solicitudes = SolicitudCambio.objects.select_related(
		"asignacion__horario", "asignacion__semestre",
		"solicitante", "monitor_reemplazo"
	).order_by("-fecha_creacion")

	return render(request, "cambios/lista_solicitudes.html", {
		"solicitudes": solicitudes,
	})


@admin_required
@require_http_methods(["GET", "POST"])
def responder_solicitud_view(request, id_cambio):
	"""Vista para que el administrador apruebe o rechace una solicitud."""
	solicitud = get_object_or_404(SolicitudCambio, pk=id_cambio)

	if solicitud.estado != SolicitudCambio.PENDIENTE:
		messages.warning(request, "Esta solicitud ya fue respondida.")
		return redirect("lista_solicitudes")

	if request.method == "POST":
		form = ResponderSolicitudForm(request.POST)
		if form.is_valid():
			estado = form.cleaned_data["estado"]
			respuesta = form.cleaned_data["respuesta"]
			try:
				if estado == SolicitudCambio.APROBADA:
					aprobar_solicitud(
						solicitud=solicitud,
						admin=request.user,
						respuesta=respuesta,
					)
					messages.success(request, "Solicitud aprobada exitosamente.")
				else:
					rechazar_solicitud(
						solicitud=solicitud,
						admin=request.user,
						respuesta=respuesta,
					)
					messages.success(request, "Solicitud rechazada exitosamente.")
				return redirect("lista_solicitudes")
			except ValidationError as exc:
				messages.error(request, str(exc))
	else:
		form = ResponderSolicitudForm()

	return render(request, "cambios/responder_solicitud.html", {
		"solicitud": solicitud,
		"form": form,
	})


@admin_required
@require_http_methods(["GET"])
def detalle_solicitud_view(request, id_cambio):
	"""Vista para que el administrador vea los detalles de una solicitud."""
	solicitud = get_object_or_404(SolicitudCambio, pk=id_cambio)
	return render(request, "cambios/detalle_solicitud.html", {
		"solicitud": solicitud,
	})
