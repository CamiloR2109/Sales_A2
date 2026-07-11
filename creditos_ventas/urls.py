from django.urls import path
from . import views

app_name = 'creditos_ventas'

urlpatterns = [
    path('facturas/', views.FacturaVentaListView.as_view(), name='factura_list'),
    path('facturas/<int:pk>/', views.FacturaVentaDetailView.as_view(), name='factura_detail'),
    path('facturas/<int:pk>/editar/', views.FacturaVentaUpdateView.as_view(), name='factura_update'),
    path('facturas/<int:pk>/eliminar/', views.FacturaVentaDeleteView.as_view(), name='factura_delete'),
    path('facturas/<int:pk>/generar-cuotas/', views.GenerarCuotasView.as_view(), name='generar_cuotas'),
    path('facturas/<int:pk>/pagos/nuevo/', views.RegistrarPagoUnificadoView.as_view(), name='registrar_pago_unificado'),
    path('facturas/<int:pk>/pagos-pdf/', views.FacturaVentaPagosPdfView.as_view(), name='factura_pagos_pdf'),

    path('cuotas/<int:pk>/eliminar/', views.CuotaVentaDeleteView.as_view(), name='cuota_delete'),
    path('cuotas/<int:cuota_pk>/pagar/', views.RegistrarPagoView.as_view(), name='registrar_pago'),

    path('comprobantes/<int:pk>/', views.ComprobantePagoDetailView.as_view(), name='comprobante_detail'),
]
