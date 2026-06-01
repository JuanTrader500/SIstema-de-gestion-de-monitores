from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class Asignacion(models.Model):
	id_asignacion = models.AutoField(primary_key=True)
	monitor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="asignaciones",
	)
	horario = models.ForeignKey(
		"horarios.Horario",
		on_delete=models.PROTECT,
		related_name="asignaciones",
	)
	semestre = models.ForeignKey(
		"semestres.Semestre",
		on_delete=models.PROTECT,
		related_name="asignaciones",
	)
	fecha_creacion = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = "Asignación"
		verbose_name_plural = "Asignaciones"
		constraints = [
			models.UniqueConstraint(
				fields=["horario", "semestre"],
				name="uq_asig_horario_semestre",
			),
			models.UniqueConstraint(
				fields=["monitor", "horario", "semestre"],
				name="uq_asig_monitor_horario_semestre",
			),
		]

	def clean(self):
		if getattr(self.monitor, "rol", None) and self.monitor.rol != "monitor":
			raise ValidationError({"monitor": "El usuario asignado debe tener rol Monitor."})

		if not self.monitor_id or not self.horario_id or not self.semestre_id:
			return

		conflicto = (
			Asignacion.objects.filter(
				monitor_id=self.monitor_id,
				semestre_id=self.semestre_id,
				horario__dia_semana=self.horario.dia_semana,
			)
			.exclude(pk=self.pk)
			.filter(
				horario__hora_inicio__lt=self.horario.hora_fin,
				horario__hora_fin__gt=self.horario.hora_inicio,
			)
			.exists()
		)
		if conflicto:
			raise ValidationError(
				"El monitor ya tiene una asignación que se cruza con este horario en el mismo semestre."
			)

	def save(self, *args, validate=True, **kwargs):
		if validate:
			self.full_clean()
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.monitor} -> {self.horario} [{self.semestre}]"
