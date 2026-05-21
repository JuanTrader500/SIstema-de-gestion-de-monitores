from datetime import time

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from horarios.models import Horario
from salas.models import Sala
from semestres.models import Semestre
from usuarios.models import Usuario
from usuarios.views import admin_required

from .forms import CrearAsignacionesForm
from .models import Asignacion
from .services import crear_asignaciones


def _fmt_hora(hora) -> str:
	return hora.strftime("%H:%M")


def _validation_error_to_text(exc: ValidationError) -> str:
	# Normaliza ValidationError (message_dict / messages) a un texto para mostrar.
	if hasattr(exc, "message_dict") and exc.message_dict:
		msgs: list[str] = []
		for _field, field_msgs in exc.message_dict.items():
			msgs.extend([str(m) for m in field_msgs])
		return " ".join(m for m in msgs if m)
	return " ".join(exc.messages) if getattr(exc, "messages", None) else str(exc)


@admin_required
@require_http_methods(["GET", "POST"])
def crear_asignacion_view(request):
	semestres_qs = Semestre.objects.order_by("-anio", "-periodo")

	semestre_activo = semestres_qs.filter(activo=True).first()
	semestre_default = semestre_activo or semestres_qs.first()

	selected_sala_id = request.GET.get("sala_id") or request.POST.get("sala_id")
	selected_semestre_id = request.GET.get("semestre") or request.POST.get("semestre")
	selected_monitor_email = request.GET.get("monitor") or request.POST.get("monitor")

	if not selected_semestre_id and semestre_default is not None:
		selected_semestre_id = str(semestre_default.pk)

	selected_sala = None
	if selected_sala_id:
		selected_sala = Sala.objects.filter(id_sala=selected_sala_id).first()

	selected_semestre = None
	if selected_semestre_id:
		selected_semestre = Semestre.objects.filter(pk=selected_semestre_id).first()

	selected_monitor = None
	if selected_monitor_email:
		selected_monitor = Usuario.objects.filter(
			email=selected_monitor_email, rol=Usuario.MONITOR
		).first()

	if request.method == "POST":
		form = CrearAsignacionesForm(
			request.POST,
			monitor_queryset=Usuario.objects.filter(rol=Usuario.MONITOR).order_by("email"),
			semestre_queryset=semestres_qs,
		)

		if form.is_valid():
			monitor = form.cleaned_data["monitor"]
			semestre = form.cleaned_data["semestre"]
			sala = form.cleaned_data["sala"]
			sala_id = sala.id_sala
			selecciones = form.cleaned_data["horarios"]
			try:
				creadas = crear_asignaciones(
					monitor=monitor,
					semestre=semestre,
					sala_id=sala_id,
					seleccion_tokens=selecciones,
				)
			except ValidationError as exc:
				form.add_error(None, _validation_error_to_text(exc) or str(exc))
			else:
				messages.success(
					request,
					f"Asignaciones creadas correctamente: {creadas}.",
				)
				return redirect("admin_dashboard")
	else:
		initial = {}
		if selected_monitor_email:
			initial["monitor"] = selected_monitor_email
		if selected_semestre_id:
			initial["semestre"] = selected_semestre_id
		if selected_sala is not None:
			initial["sala"] = selected_sala.pk

		form = CrearAsignacionesForm(
			initial=initial,
			monitor_queryset=Usuario.objects.filter(rol=Usuario.MONITOR).order_by("email"),
			semestre_queryset=semestres_qs,
		)

	# Construcción de grilla para la sala/semestre seleccionados
	dias = list(getattr(Horario, "DIAS", []))
	grid_rows = []
	asignaciones_por_horario = {}
	selected_keys_set: set[str] = set()

	# Mantener selección en caso de POST inválido
	if request.method == "POST":
		raw_selected = request.POST.get("horarios") or ""
		selected_keys_set = {x.strip() for x in raw_selected.split(",") if x.strip()}

	# Asignaciones existentes del monitor seleccionado (en cualquier sala),
	# indexadas por día para búsqueda O(1) por día.
	monitor_by_day: dict[int, list[tuple[time, time]]] = {}
	if selected_monitor is not None and selected_semestre is not None:
		for a in Asignacion.objects.filter(
			monitor=selected_monitor,
			semestre=selected_semestre,
		).select_related("horario").iterator():
			monitor_by_day.setdefault(a.horario.dia_semana, []).append(
				(a.horario.hora_inicio, a.horario.hora_fin)
			)

	if selected_sala is not None and selected_semestre is not None:
		horarios_sala = list(
			Horario.objects.filter(sala=selected_sala)
			.order_by("hora_inicio", "hora_fin", "dia_semana")
		)

		asignaciones = list(
			Asignacion.objects.filter(
				semestre=selected_semestre,
				horario__sala=selected_sala,
			).select_related("monitor", "horario")
		)
		asignaciones_por_horario = {a.horario_id: a for a in asignaciones}

		# Franjas (hora_inicio, hora_fin): si la sala no tiene, usar global; si no hay global, usar defaults.
		default_franjas = {
			(time(8, 0), time(10, 0)),
			(time(10, 0), time(12, 0)),
			(time(12, 0), time(14, 0)),
			(time(14, 0), time(16, 0)),
			(time(16, 0), time(18, 0)),
			(time(20, 0), time(22, 0)),
		}
		sala_franjas = {(h.hora_inicio, h.hora_fin) for h in horarios_sala}
		global_franjas = set(
			Horario.objects.values_list("hora_inicio", "hora_fin").distinct()
		)
		franjas = sorted(default_franjas | global_franjas | sala_franjas, key=lambda x: (x[0], x[1]))

		# Mapa (dia, inicio, fin) -> Horario
		horario_map = {
			(h.dia_semana, h.hora_inicio, h.hora_fin): h
			for h in horarios_sala
		}

		# Para bloquear creación de franjas que se cruzan con un horario ya existente.
		horarios_por_dia: dict[int, list[Horario]] = {}
		for h in horarios_sala:
			horarios_por_dia.setdefault(h.dia_semana, []).append(h)

		for inicio, fin in franjas:
			row = {
				"label": f"{_fmt_hora(inicio)} - {_fmt_hora(fin)}",
				"inicio": inicio,
				"fin": fin,
				"cells": [],
			}
			for dia_value, _dia_label in dias:
				horario = horario_map.get((dia_value, inicio, fin))
				if horario is not None:
					asignacion = asignaciones_por_horario.get(horario.id_horario)
					if asignacion is not None:
						monitor_name = asignacion.monitor.get_full_name() or asignacion.monitor.email
						row["cells"].append(
							{
								"status": "occupied",
								"horario_id": horario.id_horario,
								"monitor": monitor_name,
								"monitor_email": asignacion.monitor.email,
							}
						)
					else:
						# Verificar si el monitor seleccionado ya tiene turno a esta hora
						is_monitor_busy = any(
							s < fin and e > inicio
							for s, e in monitor_by_day.get(dia_value, [])
						)
						if is_monitor_busy:
							row["cells"].append(
								{
									"status": "monitor_busy",
									"key": f"h:{horario.id_horario}",
									"horario_id": horario.id_horario,
								}
							)
						else:
							row["cells"].append(
								{
									"status": "available",
									"key": f"h:{horario.id_horario}",
									"horario_id": horario.id_horario,
								}
							)
					continue

				# No existe horario exacto: permitir crear si no se cruza con uno existente.
				overlap = any(
					h.hora_inicio < fin and h.hora_fin > inicio
					for h in horarios_por_dia.get(dia_value, [])
				)
				if overlap:
					row["cells"].append({"status": "none"})
				else:
					# Verificar si el monitor seleccionado ya tiene turno a esta hora
					is_monitor_busy = any(
						s < fin and e > inicio
						for s, e in monitor_by_day.get(dia_value, [])
					)
					if is_monitor_busy:
						row["cells"].append(
							{
								"status": "monitor_busy",
								"key": f"n:{dia_value}|{_fmt_hora(inicio)}|{_fmt_hora(fin)}",
							}
						)
					else:
						row["cells"].append(
							{
								"status": "available",
								"key": f"n:{dia_value}|{_fmt_hora(inicio)}|{_fmt_hora(fin)}",
							}
						)

			grid_rows.append(row)

	context = {
		"form": form,
		"selected_sala": selected_sala,
		"selected_semestre": selected_semestre,
		"dias": dias,
		"grid_rows": grid_rows,
		"selected_keys": selected_keys_set,
		"admin_username": request.user.username,
	}
	return render(request, "asignaciones/crear_asignacion.html", context)
