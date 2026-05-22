from django.urls import path
from . import views

app_name = "monitores"

urlpatterns = [
    path("", views.listar_monitores, name="listar"),
    path("crear/", views.crear_monitor, name="crear"),
    path("<int:id_monitor>/editar/", views.editar_monitor, name="editar"),
    path("<int:id_monitor>/eliminar/", views.eliminar_monitor, name="eliminar"),
]
