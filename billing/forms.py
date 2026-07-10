from django import forms
from .models import Brand, Product, Warehouse
from django.forms import inlineformset_factory
from .models import Invoice, InvoiceDetail


class ProductForm(forms.ModelForm):
    """
    Formulario centralizado para crear y editar productos.
    Contiene widgets, validaciones, estilos y lógica visual.
    Reutilizado por ProductCreateView y ProductUpdateView.
    """
    class Meta:
        model = Product
        fields = [
            'name', 'description', 'brand', 'group', 'suppliers',
            'unit_price', 'stock', 'image', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Laptop HP Pavilion 15',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Descripción breve del producto...',
                'rows': 3,
            }),
            'brand': forms.Select(attrs={
                'class': 'form-select',
            }),
            'group': forms.Select(attrs={
                'class': 'form-select',
            }),
            'suppliers': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': 4,
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01',
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'min': '0',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        help_texts = {
            'name': 'Nombre comercial del producto.',
            'description': 'Opcional. Agrega detalles o especificaciones.',
            'brand': 'Selecciona la marca del producto.',
            'group': 'Categoría o grupo al que pertenece.',
            'suppliers': 'Mantén Ctrl para seleccionar varios proveedores.',
            'unit_price': 'Precio de venta al público. Debe ser mayor que cero.',
            'stock': 'Cantidad disponible en inventario.',
            'image': 'Imagen del producto (JPG, PNG). Opcional.',
            'is_active': 'Desmarcar para ocultar el producto del sistema.',
        }
        error_messages = {
            'name': {
                'required': 'El nombre del producto es obligatorio.',
                'max_length': 'El nombre no puede superar los 200 caracteres.',
            },
            'brand': {
                'required': 'Debes seleccionar una marca.',
            },
            'group': {
                'required': 'Debes seleccionar un grupo o categoría.',
            },
            'unit_price': {
                'required': 'El precio unitario es obligatorio.',
                'invalid': 'Ingresa un valor numérico válido.',
            },
        }

    def clean_unit_price(self):
        """Validación backend: el precio debe ser estrictamente mayor que cero."""
        price = self.cleaned_data.get('unit_price')
        if price is not None and price <= 0:
            raise forms.ValidationError('El precio unitario debe ser mayor que cero.')
        return price

class InvoiceForm(forms.ModelForm):
    """Formulario para cabecera de factura."""
    class Meta:
        model = Invoice
        fields = ['customer']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
        }

# Formset: permite agregar MÚLTIPLES detalles dentro de UNA factura
# extra=3: muestra 3 filas vacías para agregar productos
# can_delete=True: permite eliminar filas
InvoiceDetailFormSet = inlineformset_factory(
    Invoice,           # Modelo padre
    InvoiceDetail,     # Modelo hijo
    fields=['product', 'quantity', 'unit_price'],
    extra=3,           # 3 filas vacías para agregar
    can_delete=True,   # Checkbox para eliminar filas
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    }
)

class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'description': forms.Textarea(attrs={'class':'form-control','rows':3}),
            'is_active': forms.CheckboxInput(attrs={'class':'form-check-input'}),
        }

class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'location', 'capacity', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }