from django import forms
from django.utils import timezone

from purchasing.models import Purchase
from .models import CuotaCompra, PagoCuotaCompra


class DefinirTipoPagoCompraForm(forms.ModelForm):
    """
    Formulario para fijar si una compra es al contado o a crédito.
    Si es a crédito, además pide el número de cuotas mensuales a generar.
    """
    numero_cuotas = forms.IntegerField(
        min_value=1,
        required=False,
        label='Cantidad de cuotas mensuales',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
    )

    class Meta:
        model = Purchase
        fields = ['tipo_pago']
        widgets = {
            'tipo_pago': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()

        if self.instance.pk and self.instance.estado == Purchase.ESTADO_PAGADA:
            raise forms.ValidationError('No se puede modificar una compra que ya está PAGADA.')

        tipo_pago = cleaned_data.get('tipo_pago')
        numero_cuotas = cleaned_data.get('numero_cuotas')

        if tipo_pago == Purchase.TIPO_PAGO_CREDITO:
            if not numero_cuotas or numero_cuotas < 1:
                self.add_error('numero_cuotas', 'Debes indicar la cantidad de cuotas mensuales (mínimo 1).')
            if self.instance.pk and self.instance.cuotas.exists():
                raise forms.ValidationError('Esta compra ya tiene cuotas generadas; no se puede redefinir el plan de pago.')

        return cleaned_data


class PagoCuotaCompraForm(forms.Form):
    """
    Formulario de registro de pago. No es un ModelForm porque la creación
    real ocurre en CuotaCompra.registrar_pago(), que bloquea la fila de la
    cuota (select_for_update) antes de validar/aplicar el pago — así se
    evita una condición de carrera entre "validar en el form" y "guardar".
    Aun así se valida aquí de entrada para dar feedback inmediato al usuario.
    """
    fecha = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    valor = forms.DecimalField(
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
    )
    observacion = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def __init__(self, *args, cuota=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cuota = cuota

    def clean_valor(self):
        valor = self.cleaned_data.get('valor')
        if valor is None or valor <= 0:
            raise forms.ValidationError('El valor del pago debe ser mayor que cero.')
        if self.cuota is not None and valor > self.cuota.saldo:
            raise forms.ValidationError(
                f'El pago (${valor}) no puede superar el saldo actual de la cuota (${self.cuota.saldo}).'
            )
        return valor

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if fecha is None:
            return fecha
        if fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de pago no puede ser una fecha futura.')
        if self.cuota is not None:
            compra_fecha = self.cuota.compra.purchase_date.date()
            if fecha < compra_fecha:
                raise forms.ValidationError('La fecha de pago no puede ser anterior a la fecha de la compra.')
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        if self.cuota is not None and self.cuota.estado == CuotaCompra.ESTADO_PAGADA:
            raise forms.ValidationError('Esta cuota ya está PAGADA; no admite más pagos.')
        return cleaned_data
