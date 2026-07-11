from django import forms
from django.utils import timezone

from billing.models import Invoice
from .models import CuotaVenta, PagoCuotaVenta


class DefinirTipoPagoForm(forms.ModelForm):
    """
    Formulario para fijar si una factura es al contado o a crédito.
    Si es a crédito, además pide el número de cuotas mensuales a generar.
    """
    numero_cuotas = forms.IntegerField(
        min_value=1,
        required=False,
        label='Cantidad de cuotas mensuales',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
    )

    class Meta:
        model = Invoice
        fields = ['tipo_pago']
        widgets = {
            'tipo_pago': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()

        if self.instance.pk and self.instance.estado == Invoice.ESTADO_PAGADA:
            raise forms.ValidationError('No se puede modificar una factura que ya está PAGADA.')

        tipo_pago = cleaned_data.get('tipo_pago')
        numero_cuotas = cleaned_data.get('numero_cuotas')

        if tipo_pago == Invoice.TIPO_PAGO_CREDITO:
            if not numero_cuotas or numero_cuotas < 1:
                self.add_error('numero_cuotas', 'Debes indicar la cantidad de cuotas mensuales (mínimo 1).')
            if self.instance.pk and self.instance.cuotas.exists():
                raise forms.ValidationError('Esta factura ya tiene cuotas generadas; no se puede redefinir el plan de pago.')

        return cleaned_data


class PagoCuotaForm(forms.ModelForm):
    """Formulario para registrar un abono a una cuota de venta."""

    class Meta:
        model = PagoCuotaVenta
        fields = ['fecha', 'valor', 'observacion']
        widgets = {
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'observacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, cuota=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cuota = cuota or getattr(self.instance, 'cuota', None)

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
            factura_fecha = self.cuota.factura.invoice_date.date()
            if fecha < factura_fecha:
                raise forms.ValidationError('La fecha de pago no puede ser anterior a la fecha de la factura.')
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        if self.cuota is not None and self.cuota.estado == CuotaVenta.ESTADO_PAGADA:
            raise forms.ValidationError('Esta cuota ya está PAGADA; no admite más pagos.')
        return cleaned_data

    def save(self, commit=True):
        pago = super().save(commit=False)
        pago.cuota = self.cuota
        if commit:
            pago.save()
        return pago


class PagoUnificadoForm(forms.Form):
    """
    Permite seleccionar varias cuotas pendientes de una misma factura y
    registrarles un pago en una sola operación (un ComprobantePago).
    Los campos por cuota ('pagar_<id>' / 'valor_<id>') se generan dinámicamente
    en __init__ a partir de las cuotas PENDIENTE de la factura.
    """
    fecha = forms.DateField(
        label='Fecha de pago',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    observacion = forms.CharField(
        required=False, label='Observación',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def __init__(self, *args, factura=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.factura = factura
        self.cuotas = list(factura.cuotas.filter(estado=CuotaVenta.ESTADO_PENDIENTE).order_by('numero'))
        for cuota in self.cuotas:
            self.fields[f'pagar_{cuota.id}'] = forms.BooleanField(
                required=False, label=f'Cuota {cuota.numero}',
            )
            self.fields[f'valor_{cuota.id}'] = forms.DecimalField(
                required=False, max_digits=10, decimal_places=2, initial=cuota.saldo,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            )

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if fecha is None:
            return fecha
        if fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de pago no puede ser una fecha futura.')
        if self.factura and fecha < self.factura.invoice_date.date():
            raise forms.ValidationError('La fecha de pago no puede ser anterior a la fecha de la factura.')
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        seleccionadas = []
        for cuota in self.cuotas:
            if not cleaned_data.get(f'pagar_{cuota.id}'):
                continue
            valor = cleaned_data.get(f'valor_{cuota.id}')
            if valor is None or valor <= 0:
                self.add_error(f'valor_{cuota.id}', 'Ingresa un valor mayor que cero.')
                continue
            if valor > cuota.saldo:
                self.add_error(f'valor_{cuota.id}', f'No puede superar el saldo actual (${cuota.saldo}).')
                continue
            seleccionadas.append((cuota, valor))

        if not seleccionadas and not self.errors:
            raise forms.ValidationError('Selecciona al menos una cuota y su valor a pagar.')

        cleaned_data['seleccionadas'] = seleccionadas
        return cleaned_data
