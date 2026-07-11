from django.contrib import admin

from .models import CuotaCompra, PagoCuotaCompra


class PagoCuotaCompraInline(admin.TabularInline):
    model = PagoCuotaCompra
    extra = 0
    readonly_fields = ['fecha', 'valor', 'observacion']
    can_delete = False


@admin.register(CuotaCompra)
class CuotaCompraAdmin(admin.ModelAdmin):
    list_display = ['compra', 'numero', 'fecha_vencimiento', 'valor', 'saldo', 'estado']
    list_filter = ['estado']
    search_fields = ['compra__id', 'compra__supplier__name']
    inlines = [PagoCuotaCompraInline]


@admin.register(PagoCuotaCompra)
class PagoCuotaCompraAdmin(admin.ModelAdmin):
    list_display = ['cuota', 'fecha', 'valor']
    list_filter = ['fecha']
