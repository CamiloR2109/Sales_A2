from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver

from billing.models import Invoice
from .models import CuotaVenta, PagoCuotaVenta


@receiver(post_save, sender=PagoCuotaVenta)
def actualizar_saldo_cuota_y_factura(sender, instance, created, **kwargs):
    """
    Al registrar un pago:
    1) descuenta el valor pagado del saldo de la cuota y la marca PAGADA si llega a 0.
    2) recalcula el saldo de la factura como la suma de saldos de sus cuotas.
    3) si ya no quedan cuotas pendientes, marca la factura como PAGADA.
    """
    if not created:
        return

    cuota = instance.cuota
    cuota.saldo = cuota.saldo - instance.valor
    if cuota.saldo <= 0:
        cuota.saldo = Decimal('0.00')
        cuota.estado = CuotaVenta.ESTADO_PAGADA
    cuota.save(update_fields=['saldo', 'estado'])

    factura = cuota.factura
    saldo_total = factura.cuotas.aggregate(total=Sum('saldo'))['total'] or Decimal('0.00')
    factura.saldo = saldo_total
    if not factura.cuotas.exclude(estado=CuotaVenta.ESTADO_PAGADA).exists():
        factura.estado = Invoice.ESTADO_PAGADA
    factura.save(update_fields=['saldo', 'estado'])

    if instance.comprobante_id:
        instance.comprobante.recalcular_total()
