from django.urls import path
from . import views

app_name = "horarios"

urlpatterns = [
    path("", views.listar_horarios, name="listar"),
    path("crear/", views.crear_horario, name="crear-horario"),
    path("<int:id_horario>/editar/", views.editar_horario, name="editar-horario"),
    path("<int:id_horario>/eliminar/", views.eliminar_horario, name="eliminar-horario"),
]
