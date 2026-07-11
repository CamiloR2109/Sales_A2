from decimal import Decimal, ROUND_DOWN

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from purchasing.models import Purchase


def _sumar_meses(fecha, meses):
    """Suma 'meses' meses calendario a una fecha, sin depender de dateutil."""
    mes_total = fecha.month - 1 + meses
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(fecha.day, [31, 29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1])
    return fecha.replace(year=anio, month=mes, day=dia)


class CuotaCompra(models.Model):
    """Cuota mensual generada al registrar una compra a crédito."""
    ESTADO_PENDIENTE = 'PENDIENTE'
    ESTADO_PAGADA = 'PAGADA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_PAGADA, 'Pagada'),
    ]

    compra = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name='cuotas')
    numero = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)

    class Meta:
        verbose_name = 'Cuota de Compra'
        verbose_name_plural = 'Cuotas de Compra'
        ordering = ['compra', 'numero']
        unique_together = [('compra', 'numero')]

    def __str__(self):
        return f'Cuota {self.numero} - Compra #{self.compra_id}'

    def clean(self):
        if self.valor is not None and self.valor <= 0:
            raise ValidationError({'valor': 'El valor de la cuota debe ser mayor que cero.'})

    @classmethod
    def generar_para_compra(cls, compra, numero_cuotas):
        """
        Genera las cuotas mensuales de una compra a crédito, dividiendo el
        total entre el número de cuotas. Ajusta el redondeo en la última
        cuota para que la suma sea exactamente igual al total de la compra.
        """
        if numero_cuotas is None or numero_cuotas < 1:
            raise ValidationError('La cantidad de cuotas debe ser al menos 1.')
        if compra.tipo_pago != Purchase.TIPO_PAGO_CREDITO:
            raise ValidationError('Solo se pueden generar cuotas para compras a crédito.')
        if compra.cuotas.exists():
            raise ValidationError('Esta compra ya tiene cuotas generadas.')

        total = Decimal(str(compra.total))
        valor_base = (total / numero_cuotas).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        fecha_base = compra.purchase_date.date()

        acumulado = Decimal('0.00')
        cuotas = []
        for numero in range(1, numero_cuotas + 1):
            if numero < numero_cuotas:
                valor = valor_base
            else:
                valor = total - acumulado  # última cuota absorbe el residuo del redondeo
            acumulado += valor
            cuotas.append(cls(
                compra=compra,
                numero=numero,
                fecha_vencimiento=_sumar_meses(fecha_base, numero),
                valor=valor,
                saldo=valor,
            ))

        cls.objects.bulk_create(cuotas)
        compra.marcar_como_credito()
        return cuotas

    @classmethod
    @transaction.atomic
    def registrar_pago(cls, cuota_id, fecha, valor, observacion=''):
        """
        Registra un pago sobre una cuota de forma segura ante concurrencia:
        bloquea la fila de la cuota (y luego la de la compra) con
        select_for_update() ANTES de leer/validar el saldo, de modo que dos
        pagos simultáneos sobre la misma cuota queden serializados por la
        base de datos en vez de perder una actualización (lost update).
        Ver explicación detallada al final de la respuesta.
        """
        cuota = cls.objects.select_for_update().get(pk=cuota_id)

        if cuota.estado == cls.ESTADO_PAGADA:
            raise ValidationError('Esta cuota ya está PAGADA; no admite más pagos.')
        if valor is None or valor <= 0:
            raise ValidationError('El valor del pago debe ser mayor que cero.')
        if valor > cuota.saldo:
            raise ValidationError(f'El pago (${valor}) no puede superar el saldo actual de la cuota (${cuota.saldo}).')
        if fecha is not None:
            if fecha > timezone.localdate():
                raise ValidationError('La fecha de pago no puede ser una fecha futura.')
            if fecha < cuota.compra.purchase_date.date():
                raise ValidationError('La fecha de pago no puede ser anterior a la fecha de la compra.')

        pago = PagoCuotaCompra.objects.create(cuota=cuota, fecha=fecha, valor=valor, observacion=observacion)

        cuota.saldo = cuota.saldo - valor
        if cuota.saldo <= 0:
            cuota.saldo = Decimal('0.00')
            cuota.estado = cls.ESTADO_PAGADA
        cuota.save(update_fields=['saldo', 'estado'])

        compra = Purchase.objects.select_for_update().get(pk=cuota.compra_id)
        saldo_total = compra.cuotas.aggregate(total=Sum('saldo'))['total'] or Decimal('0.00')
        compra.saldo = saldo_total
        if not compra.cuotas.exclude(estado=cls.ESTADO_PAGADA).exists():
            compra.estado = Purchase.ESTADO_PAGADA
        compra.save(update_fields=['saldo', 'estado'])

        return pago


class PagoCuotaCompra(models.Model):
    """Registro de un abono a una cuota de compra a crédito."""
    cuota = models.ForeignKey(CuotaCompra, on_delete=models.PROTECT, related_name='pagos')
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Pago de Cuota de Compra'
        verbose_name_plural = 'Pagos de Cuota de Compra'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'Pago ${self.valor} - Cuota {self.cuota_id}'

    def clean(self):
        if self.valor is not None and self.valor <= 0:
            raise ValidationError({'valor': 'El valor del pago debe ser mayor que cero.'})
        if self.cuota_id and self.valor is not None and self.valor > self.cuota.saldo:
            raise ValidationError({'valor': 'El pago no puede superar el saldo actual de la cuota.'})
        if self.fecha and self.cuota_id:
            compra_fecha = self.cuota.compra.purchase_date.date()
            if self.fecha < compra_fecha:
                raise ValidationError({'fecha': 'La fecha de pago no puede ser anterior a la fecha de la compra.'})
        if self.fecha and self.fecha > timezone.localdate():
            raise ValidationError({'fecha': 'La fecha de pago no puede ser una fecha futura.'})
