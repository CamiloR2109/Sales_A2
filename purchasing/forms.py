from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory
from .models import Purchase, PurchaseDetail

class PurchaseForm(forms.ModelForm):
    """Formulario para cabecera de factura."""
    class Meta:
        model = Purchase
        fields = ['supplier', 'document_number']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
        }
        
PurchaseDetailFormSet = inlineformset_factory(
    Purchase,           # Modelo padre
    PurchaseDetail,     # Modelo hijo
    fields=['product', 'quantity', 'unit_cost'],
    extra=3,           # 3 filas vacías para agregar
    can_delete=True,   # Checkbox para eliminar filas
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    }
)