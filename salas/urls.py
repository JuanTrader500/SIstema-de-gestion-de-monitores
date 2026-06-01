from django.urls import path
from . import views

app_name = "salas"

urlpatterns = [
    path("", views.listar_salas, name="listar"),
    path("crear/", views.crear_sala, name="crear-sala"),
    path("<int:id_sala>/editar/", views.editar_sala, name="editar-sala"),
    path("<int:id_sala>/eliminar/", views.eliminar_sala, name="eliminar-sala"),
]
