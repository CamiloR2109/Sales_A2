from decimal import Decimal, ROUND_DOWN

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from billing.models import Customer, Invoice


def _sumar_meses(fecha, meses):
    """Suma 'meses' meses calendario a una fecha, sin depender de dateutil."""
    mes_total = fecha.month - 1 + meses
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(fecha.day, [31, 29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1])
    return fecha.replace(year=anio, month=mes, day=dia)


class CuotaVenta(models.Model):
    """Cuota mensual generada al vender una factura a crédito."""
    ESTADO_PENDIENTE = 'PENDIENTE'
    ESTADO_PAGADA = 'PAGADA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_PAGADA, 'Pagada'),
    ]

    factura = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='cuotas')
    numero = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)

    class Meta:
        verbose_name = 'Cuota de Venta'
        verbose_name_plural = 'Cuotas de Venta'
        ordering = ['factura', 'numero']
        unique_together = [('factura', 'numero')]

    def __str__(self):
        return f'Cuota {self.numero} - Factura #{self.factura_id}'

    def clean(self):
        if self.valor is not None and self.valor <= 0:
            raise ValidationError({'valor': 'El valor de la cuota debe ser mayor que cero.'})

    @classmethod
    def generar_para_factura(cls, factura, numero_cuotas):
        """
        Genera las cuotas mensuales de una factura a crédito, dividiendo el
        total entre el número de cuotas. Ajusta el redondeo en la última
        cuota para que la suma sea exactamente igual al total de la factura.
        """
        if numero_cuotas is None or numero_cuotas < 1:
            raise ValidationError('La cantidad de cuotas debe ser al menos 1.')
        if factura.tipo_pago != Invoice.TIPO_PAGO_CREDITO:
            raise ValidationError('Solo se pueden generar cuotas para facturas a crédito.')
        if factura.cuotas.exists():
            raise ValidationError('Esta factura ya tiene cuotas generadas.')

        total = Decimal(str(factura.total))
        valor_base = (total / numero_cuotas).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        fecha_base = factura.invoice_date.date()

        acumulado = Decimal('0.00')
        cuotas = []
        for numero in range(1, numero_cuotas + 1):
            if numero < numero_cuotas:
                valor = valor_base
            else:
                valor = total - acumulado  # última cuota absorbe el residuo del redondeo
            acumulado += valor
            cuotas.append(cls(
                factura=factura,
                numero=numero,
                fecha_vencimiento=_sumar_meses(fecha_base, numero),
                valor=valor,
                saldo=valor,
            ))

        cls.objects.bulk_create(cuotas)
        factura.marcar_como_credito()
        return cuotas


class ComprobantePago(models.Model):
    """
    Agrupa uno o varios PagoCuotaVenta registrados en una misma operación,
    como recibo formal de caja. No guarda 'factura' ni 'total_pagado' como
    datos de entrada: factura se deriva de pagos->cuota->factura (evita
    redundancia / 3FN) y total_pagado es un valor cacheado que SIEMPRE se
    recalcula con Sum() sobre los pagos asociados (ver signals.py), nunca
    se edita a mano.
    """
    numero_comprobante = models.CharField(max_length=20, unique=True, editable=False)
    fecha_emision = models.DateTimeField(auto_now_add=True)
    cliente = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='comprobantes_pago')
    total_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)

    class Meta:
        verbose_name = 'Comprobante de Pago'
        verbose_name_plural = 'Comprobantes de Pago'
        ordering = ['-fecha_emision']

    def __str__(self):
        return self.numero_comprobante

    def save(self, *args, **kwargs):
        if not self.numero_comprobante:
            self.numero_comprobante = self._generar_numero()
        super().save(*args, **kwargs)

    @staticmethod
    def _generar_numero():
        """Numeración secuencial 'CP-000001', protegida contra condiciones de carrera."""
        with transaction.atomic():
            ultimo = ComprobantePago.objects.select_for_update().order_by('-id').first()
            siguiente = (ultimo.id + 1) if ultimo else 1
            return f'CP-{siguiente:06d}'

    def recalcular_total(self):
        """Recalcula total_pagado sumando (Sum) los pagos asociados. Idempotente."""
        total = self.pagos.aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        self.total_pagado = total
        self.save(update_fields=['total_pagado'])


class PagoCuotaVenta(models.Model):
    """Registro de un abono a una cuota de venta a crédito."""
    cuota = models.ForeignKey(CuotaVenta, on_delete=models.PROTECT, related_name='pagos')
    comprobante = models.ForeignKey(
        ComprobantePago, on_delete=models.PROTECT, related_name='pagos',
        null=True, blank=True,
    )
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Pago de Cuota'
        verbose_name_plural = 'Pagos de Cuota'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'Pago ${self.valor} - Cuota {self.cuota_id}'

    def clean(self):
        if self.valor is not None and self.valor <= 0:
            raise ValidationError({'valor': 'El valor del pago debe ser mayor que cero.'})
        if self.cuota_id and self.valor is not None and self.valor > self.cuota.saldo:
            raise ValidationError({'valor': 'El pago no puede superar el saldo actual de la cuota.'})
        if self.fecha and self.cuota_id:
            factura_fecha = self.cuota.factura.invoice_date.date()
            if self.fecha < factura_fecha:
                raise ValidationError({'fecha': 'La fecha de pago no puede ser anterior a la fecha de la factura.'})
        if self.fecha and self.fecha > timezone.localdate():
            raise ValidationError({'fecha': 'La fecha de pago no puede ser una fecha futura.'})
