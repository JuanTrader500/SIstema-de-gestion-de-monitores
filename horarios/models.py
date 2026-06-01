from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.db.models import Func
from salas.models import Sala

class Horario(models.Model):
    id_horario = models.AutoField(primary_key=True)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name='horarios')
    
    DIAS = [
        (1, 'Lunes'), (2, 'Martes'), (3, 'Miércoles'),
        (4, 'Jueves'), (5, 'Viernes'), (6, 'Sábado'),
    ]
    dia_semana = models.IntegerField(choices=DIAS)
    
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        constraints = [
            ExclusionConstraint(
                name='exclude_overlapping_reservations',
                expressions=[
                    # 1. La sala debe ser la misma para que haya conflicto
                    ('sala', RangeOperators.EQUAL),
                    
                    # 2. El día debe ser el mismo
                    ('dia_semana', RangeOperators.EQUAL),
                    
                    # 3. El rango de tiempo debe solaparse (&&)
                    # Convertimos hora_inicio y hora_fin en un tipo 'timerange' de Postgres
                    (
                        Func('hora_inicio', 'hora_fin', function='timerange'), 
                        RangeOperators.OVERLAPS
                    ),
                ],
            ),
        ]

    def clean(self):
        if self.hora_inicio is not None and self.hora_fin is not None:
            if self.hora_fin <= self.hora_inicio:
                raise ValidationError("La hora de fin debe ser posterior a la hora de inicio.")

    def save(self, *args, validate=True, **kwargs):
        if validate:
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_dia_semana_display()}: {self.hora_inicio.strftime('%H:%M')} - {self.hora_fin.strftime('%H:%M')} ({self.sala})"