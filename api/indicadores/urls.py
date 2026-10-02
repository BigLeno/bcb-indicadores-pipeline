from django.urls import path
from rest_framework.routers import DefaultRouter

from indicadores import views

router = DefaultRouter()
router.register("series", views.SerieViewSet, basename="serie")
router.register("valores", views.SerieValorViewSet, basename="valor")
router.register("marts/ipca-mensal", views.IpcaMensalViewSet, basename="ipca-mensal")
router.register("marts/cdi-mensal", views.CdiMensalViewSet, basename="cdi-mensal")
router.register("marts/dolar-diario", views.DolarDiarioViewSet, basename="dolar-diario")
router.register("marts/dolar-mensal", views.DolarMensalViewSet, basename="dolar-mensal")

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    *router.urls,
]
