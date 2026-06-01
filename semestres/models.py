from django.db import models
from django.db.models import Q


class Semestre(models.Model):
	PERIODO_CHOICES = [(1, "Primer semestre"), (2, "Segundo semestre")]

	id_semestre = models.AutoField(primary_key=True)
	anio = models.PositiveSmallIntegerField("Año")
	periodo = models.PositiveSmallIntegerField("Periodo", choices=PERIODO_CHOICES)
	activo = models.BooleanField(default=False)

	class Meta:
		db_table = "semestre"
		verbose_name = "Semestre"
		verbose_name_plural = "Semestres"
		ordering = ["-anio", "-periodo"]
		constraints = [
			models.UniqueConstraint(
				fields=["anio", "periodo"],
				name="uq_semestre_anio_periodo",
			),
			models.CheckConstraint(
				condition=Q(periodo__in=[1, 2]),
				name="chk_semestre_periodo_1_2",
			),
		]

	def __str__(self):
		return f"{self.anio}-{self.periodo}"
