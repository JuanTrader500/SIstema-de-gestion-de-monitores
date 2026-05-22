from django.urls import path
from . import views

app_name = "semestres"

urlpatterns = [
    path("", views.listar_semestres, name="listar"),
    path("crear/", views.crear_semestre, name="crear"),
    path("<int:id_semestre>/editar/", views.editar_semestre, name="editar"),
    path("<int:id_semestre>/eliminar/", views.eliminar_semestre, name="eliminar"),
]
