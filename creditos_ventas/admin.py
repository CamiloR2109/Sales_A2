from django.contrib import admin

from .models import ComprobantePago, CuotaVenta, PagoCuotaVenta


class PagoCuotaVentaInline(admin.TabularInline):
    model = PagoCuotaVenta
    extra = 0
    readonly_fields = ['fecha', 'valor', 'observacion', 'comprobante']
    can_delete = False


@admin.register(CuotaVenta)
class CuotaVentaAdmin(admin.ModelAdmin):
    list_display = ['factura', 'numero', 'fecha_vencimiento', 'valor', 'saldo', 'estado']
    list_filter = ['estado']
    search_fields = ['factura__id', 'factura__customer__last_name']
    inlines = [PagoCuotaVentaInline]


@admin.register(PagoCuotaVenta)
class PagoCuotaVentaAdmin(admin.ModelAdmin):
    list_display = ['cuota', 'comprobante', 'fecha', 'valor']
    list_filter = ['fecha']


@admin.register(ComprobantePago)
class ComprobantePagoAdmin(admin.ModelAdmin):
    list_display = ['numero_comprobante', 'cliente', 'fecha_emision', 'total_pagado']
    readonly_fields = ['numero_comprobante', 'fecha_emision', 'total_pagado']
    search_fields = ['numero_comprobante', 'cliente__last_name', 'cliente__first_name']
    inlines = [PagoCuotaVentaInline]
