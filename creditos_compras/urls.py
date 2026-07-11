from django.urls import path
from . import views

app_name = 'creditos_compras'

urlpatterns = [
    path('compras/', views.CompraListView.as_view(), name='compra_list'),
    path('compras/<int:pk>/', views.CompraDetailView.as_view(), name='compra_detail'),
    path('compras/<int:pk>/tipo-pago/', views.DefinirTipoPagoCompraView.as_view(), name='definir_tipo_pago'),
    path('compras/<int:pk>/eliminar/', views.CompraDeleteView.as_view(), name='compra_delete'),
    path('compras/<int:pk>/generar-cuotas/', views.GenerarCuotasCompraView.as_view(), name='generar_cuotas'),
    path('compras/<int:pk>/cuotas/', views.CuotaCompraListView.as_view(), name='cuota_list'),

    path('cuotas/pendientes/', views.CuotasPendientesListView.as_view(), name='cuotas_pendientes'),
    path('cuotas/<int:pk>/eliminar/', views.CuotaCompraDeleteView.as_view(), name='cuota_delete'),
    path('cuotas/<int:pk>/historial/', views.HistorialPagosCompraView.as_view(), name='historial_pagos'),
    path('cuotas/<int:cuota_pk>/pagar/', views.RegistrarPagoCompraView.as_view(), name='registrar_pago'),
]
