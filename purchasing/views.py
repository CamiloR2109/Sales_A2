from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from decimal import Decimal

from .models import Purchase, PurchaseDetail
from .forms import PurchaseForm, PurchaseDetailFormSet

@login_required
def purchase_list(request):
    """Lista todas las facturas con sus totales."""
    purchases = Purchase.objects.select_related('supplier').all()
    return render(request, 'purchasing/purchase_list.html', {'items': purchases})

@login_required
def purchase_create(request):
    """Crea factura con sus líneas de detalle."""
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        formset = PurchaseDetailFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            # Guardar factura (sin commit para asignar totales)
            purchase = form.save(commit=False)
            purchase.save()

            # Asignar la factura al formset y guardar detalles
            formset.instance = purchase
            details = formset.save()

            # Calcular totales
            subtotal = sum(d.subtotal for d in purchase.details.all())
            purchase.subtotal = subtotal
            purchase.tax = subtotal * Decimal('0.15')  # IVA 15%
            purchase.total = purchase.subtotal + purchase.tax
            purchase.save()

            messages.success(request, f'Purchase #{purchase.id} created! Total: ${purchase.total}')
            return redirect('purchasing:purchase_list')
    else:
        form = PurchaseForm()
        formset = PurchaseDetailFormSet()

    return render(request, 'purchasing/purchase_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create purchase',
    })
    
@login_required
def purchase_detail(request, pk):
    """Muestra el detalle completo de una factura."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier')
                    .prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'purchasing/purchase_detail.html', {'purchase': purchase})

@login_required
def purchase_delete(request, pk):
    """Elimina una factura y todos sus detalles (CASCADE)."""
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        purchase_id = purchase.id
        purchase.delete()
        messages.success(request, f'Purchase #{purchase_id} deleted!')
        return redirect('purchasing:purchase_list')
    return render(request, 'purchasing/purchase_confirm_delete.html', {'object': purchase})
