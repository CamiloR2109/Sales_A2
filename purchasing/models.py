from django.db import models
from decimal import Decimal
from billing.models import Supplier, Product   # Reutilizamos modelos de billing

class Purchase(models.Model):
    """Cabecera de compra. Documenta una adquisición a un proveedor."""
    TIPO_PAGO_CONTADO = 'CONTADO'
    TIPO_PAGO_CREDITO = 'CREDITO'
    TIPO_PAGO_CHOICES = [
        (TIPO_PAGO_CONTADO, 'Contado'),
        (TIPO_PAGO_CREDITO, 'Crédito'),
    ]
    ESTADO_PENDIENTE = 'PENDIENTE'
    ESTADO_PAGADA = 'PAGADA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_PAGADA, 'Pagada'),
    ]

    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchases'
    )
    document_number = models.CharField(
        max_length=20, verbose_name='Supplier Invoice No.'
    )
    purchase_date = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    tipo_pago = models.CharField(max_length=10, choices=TIPO_PAGO_CHOICES, default=TIPO_PAGO_CONTADO)
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)

    class Meta:
        verbose_name = 'Purchase'
        verbose_name_plural = 'Purchases'
        ordering = ['-purchase_date']
        constraints = [
            models.UniqueConstraint(
                fields=['supplier', 'document_number'],
                name='unique_supplier_document'
            )
        ]
        permissions = [
            ('export_purchase', 'Can export purchase'),
            ('print_purchase', 'Can print purchase'),
        ]

    def __str__(self):
        return f'Purchase #{self.id} - {self.supplier}'

    def marcar_como_contado(self):
        """Compras al contado quedan canceladas de inmediato: saldo 0 y estado PAGADA."""
        self.tipo_pago = self.TIPO_PAGO_CONTADO
        self.saldo = 0
        self.estado = self.ESTADO_PAGADA
        self.save(update_fields=['tipo_pago', 'saldo', 'estado'])

    def marcar_como_credito(self):
        """Compras a crédito arrancan con saldo = total, pendientes hasta cancelar todas las cuotas."""
        self.tipo_pago = self.TIPO_PAGO_CREDITO
        self.saldo = self.total
        self.estado = self.ESTADO_PENDIENTE
        self.save(update_fields=['tipo_pago', 'saldo', 'estado'])

class PurchaseDetail(models.Model):
    """Líneas de compra. Cada fila es un producto adquirido."""
    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name='details'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='purchase_details'
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_cost
        super().save(*args, **kwargs)
