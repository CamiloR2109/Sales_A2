from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from django.db.models import F
from billing.models import Product, Supplier
from shared.decorators import permission_required_redirect

from .models import Purchase, PurchaseDetail
from .forms import PurchaseForm, PurchaseDetailFormSet

@login_required
@permission_required_redirect('purchasing.view_purchase', redirect_to='billing:home')
def purchase_list(request):
    """Lista todas las compras con sus totales, con filtros de búsqueda."""
    purchases = Purchase.objects.select_related('supplier').all()
    g = request.GET

    # --- Filtro por número de documento (texto parcial) ---
    document_number = g.get('document_number', '').strip()
    if document_number:
        purchases = purchases.filter(document_number__icontains=document_number)

    # --- Filtro por proveedor (FK — select) ---
    supplier = g.get('supplier', '').strip()
    if supplier:
        purchases = purchases.filter(supplier_id=supplier)

    # --- Filtro por fecha desde ---
    date_from = g.get('date_from', '').strip()
    if date_from:
        purchases = purchases.filter(purchase_date__date__gte=date_from)

    # --- Filtro por fecha hasta ---
    date_to = g.get('date_to', '').strip()
    if date_to:
        purchases = purchases.filter(purchase_date__date__lte=date_to)

    # --- Filtro por total mínimo ---
    total_min = g.get('total_min', '').strip()
    if total_min:
        try:
            purchases = purchases.filter(total__gte=total_min)
        except (ValueError, TypeError):
            pass

    # --- Filtro por total máximo ---
    total_max = g.get('total_max', '').strip()
    if total_max:
        try:
            purchases = purchases.filter(total__lte=total_max)
        except (ValueError, TypeError):
            pass

    # --- Filtro por estado activo ---
    is_active = g.get('is_active', '').strip()
    if is_active in ('true', 'false'):
        purchases = purchases.filter(is_active=(is_active == 'true'))

    context = {
        'items': purchases,
        'suppliers': Supplier.objects.filter(is_active=True).order_by('name'),
        'current_filters': {
            'document_number': document_number,
            'supplier': supplier,
            'date_from': date_from,
            'date_to': date_to,
            'total_min': total_min,
            'total_max': total_max,
            'is_active': is_active,
        },
    }
    return render(request, 'purchasing/purchase_list.html', context)

@login_required
@permission_required_redirect('purchasing.add_purchase', redirect_to='purchasing:purchase_list')
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

            # Actualizar stock sumando la cantidad comprada (pista aplicada)
            for d in details:
                Product.objects.filter(pk=d.product_id).update(stock=F('stock') + d.quantity)

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
@permission_required_redirect('purchasing.view_purchase', redirect_to='purchasing:purchase_list')
def purchase_detail(request, pk):
    """Muestra el detalle completo de una factura."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier')
                    .prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'purchasing/purchase_detail.html', {'purchase': purchase})

@login_required
@permission_required_redirect('purchasing.delete_purchase', redirect_to='purchasing:purchase_list')
def purchase_delete(request, pk):
    """Elimina una factura y todos sus detalles (CASCADE)."""
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        purchase_id = purchase.id
        purchase.delete()
        messages.success(request, f'Purchase #{purchase_id} deleted!')
        return redirect('purchasing:purchase_list')
    return render(request, 'purchasing/purchase_confirm_delete.html', {'object': purchase})
