from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from .models import *
from shared.mixins import PermissionRequiredMixin, ExportMixin
from shared.decorators import audit_action, permission_required_redirect
from .forms import BrandForm, InvoiceForm, InvoiceDetailFormSet, ProductForm, WarehouseForm
from decimal import Decimal
from django.db.models import F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
import json


# === HOME (Página principal) ===
@login_required
def home(request):
    """Vista principal del sistema. Muestra resumen general."""
    if not request.user.is_superuser and request.user.groups.filter(name='Cliente').exists():
        return redirect('storefront:catalog')

    # Ventas de los últimos 7 días, agrupadas por día
    today = timezone.localdate()
    start_date = today - timedelta(days=6)
    daily_totals = (
        Invoice.objects.filter(invoice_date__date__gte=start_date)
        .annotate(day=TruncDate('invoice_date'))
        .values('day')
        .annotate(total=Sum('total'))
    )
    totals_by_day = {row['day']: float(row['total']) for row in daily_totals}
    sales_labels, sales_values = [], []
    for i in range(7):
        day = start_date + timedelta(days=i)
        sales_labels.append(day.strftime('%d/%m'))
        sales_values.append(totals_by_day.get(day, 0))

    # Productos con bajo stock, para el gráfico de barras
    low_stock = list(Product.objects.filter(stock__lte=5, is_active=True).order_by('stock')[:8])

    context = {
        'total_brands': Brand.objects.count(),
        'total_products': Product.objects.count(),
        'total_customers': Customer.objects.count(),
        'total_invoices': Invoice.objects.count(),
        'recent_invoices': Invoice.objects.all()[:5],  # Últimas 5
        'low_stock': low_stock,
        'sales_labels_json': json.dumps(sales_labels),
        'sales_values_json': json.dumps(sales_values),
        'has_sales_data': any(sales_values),
        'stock_labels_json': json.dumps([p.name for p in low_stock]),
        'stock_values_json': json.dumps([p.stock for p in low_stock]),
        'has_low_stock': bool(low_stock),
    }
    return render(request, 'billing/home.html', context)

class ProductGroupDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ProductGroup
    template_name = 'billing/productgroup_confirm_delete.html'
    success_url = reverse_lazy('billing:productgroup_list')
    permission_required = 'billing.delete_productgroup'
    permission_redirect_url = '/groups/'

class SupplierDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Supplier
    template_name = 'billing/supplier_confirm_delete.html'
    success_url = reverse_lazy('billing:supplier_list')
    permission_required = 'billing.delete_supplier'
    permission_redirect_url = '/suppliers/'

class ProductDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Product
    template_name = 'billing/product_confirm_delete.html'
    success_url = reverse_lazy('billing:product_list')
    permission_required = 'billing.delete_product'
    permission_redirect_url = '/products/'

class CustomerDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Customer
    template_name = 'billing/customer_confirm_delete.html'
    success_url = reverse_lazy('billing:customer_list')
    permission_required = 'billing.delete_customer'
    permission_redirect_url = '/customers/'


# === BRAND (FBV) ===
@login_required
@permission_required_redirect('billing.view_brand', redirect_to='billing:home')
@audit_action('LIST_BRANDS')
def brand_list(request):
    brands = Brand.objects.all()
    return render(request, 'billing/brand_list.html', {'brands': brands})

@login_required
@permission_required_redirect('billing.add_brand', redirect_to='billing:brand_list')
@audit_action('CREATE_BRAND')
def brand_create(request):
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand created!')
            return redirect('billing:brand_list')
    else: form = BrandForm()
    return render(request, 'billing/brand_form.html', {'form':form, 'title':'Create Brand'})

@login_required
@permission_required_redirect('billing.change_brand', redirect_to='billing:brand_list')
@audit_action('UPDATE_BRAND')
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand updated!')
            return redirect('billing:brand_list')
    else: form = BrandForm(instance=brand)
    return render(request, 'billing/brand_form.html', {'form':form, 'title':'Edit Brand'})

@login_required
@permission_required_redirect('billing.delete_brand', redirect_to='billing:brand_list')
@audit_action('DELETE_BRAND')
def brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        brand.delete()
        messages.success(request, 'Brand deleted!')
        return redirect('billing:brand_list')
    return render(request, 'billing/brand_confirm_delete.html', {'object': brand})

# === WAREHOUSE ===
@login_required
@permission_required_redirect('billing.view_warehouse', redirect_to='billing:home')
def warehouse_list(request):
    warehouses = Warehouse.objects.all()
    return render(request, 'billing/warehouse_list.html', {'warehouses': warehouses})

@login_required
@permission_required_redirect('billing.add_warehouse', redirect_to='billing:warehouse_list')
def warehouse_create(request):
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warehouse created!')
            return redirect('billing:warehouse_list')
    else:
        form = WarehouseForm()
    return render(request, 'billing/warehouse_form.html', {'form': form, 'title': 'Create Warehouse'})

@login_required
@permission_required_redirect('billing.change_warehouse', redirect_to='billing:warehouse_list')
def warehouse_update(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warehouse updated!')
            return redirect('billing:warehouse_list')
    else:
        form = WarehouseForm(instance=warehouse)
    return render(request, 'billing/warehouse_form.html', {'form': form, 'title': 'Edit Warehouse'})

@login_required
@permission_required_redirect('billing.delete_warehouse', redirect_to='billing:warehouse_list')
def warehouse_delete(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST':
        warehouse.delete()
        messages.success(request, 'Warehouse deleted!')
        return redirect('billing:warehouse_list')
    return render(request, 'billing/warehouse_confirm_delete.html', {'object': warehouse})


# === PRODUCTGROUP (CBV) ===
class ProductGroupListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ProductGroup; template_name = 'billing/productgroup_list.html'; context_object_name = 'items'
    permission_required = 'billing.view_productgroup'; permission_redirect_url = '/'
class ProductGroupCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ProductGroup; fields = ['name','is_active']; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
    permission_required = 'billing.add_productgroup'; permission_redirect_url = '/groups/'
class ProductGroupUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ProductGroup; fields = ['name','is_active']; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
    permission_required = 'billing.change_productgroup'; permission_redirect_url = '/groups/'

# === SUPPLIER (CBV) ===
class SupplierListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Supplier; template_name = 'billing/supplier_list.html'; context_object_name = 'items'
    permission_required = 'billing.view_supplier'; permission_redirect_url = '/'
class SupplierCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Supplier; fields = ['name','business_name','document_type','document_number','contact_name','email','phone','address','is_active']; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
    permission_required = 'billing.add_supplier'; permission_redirect_url = '/suppliers/'
class SupplierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Supplier; fields = ['name','business_name','document_type','document_number','contact_name','email','phone','address','is_active']; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
    permission_required = 'billing.change_supplier'; permission_redirect_url = '/suppliers/'

# === PRODUCT (CBV) ===
class ProductListView(LoginRequiredMixin, PermissionRequiredMixin, ExportMixin, ListView):
    model = Product
    template_name = 'billing/product_list.html'
    context_object_name = 'items'
    paginate_by = 10
    permission_required = 'billing.view_product'
    permission_redirect_url = '/'

    # Configuración de exportación
    export_filename = 'listado_productos'
    export_fields = ['name', 'brand.name', 'group.name', 'unit_price', 'stock', 'balance', 'is_active', 'suppliers']
    export_headers = ['Nombre', 'Marca', 'Grupo', 'Precio Unitario', 'Stock', 'Balance', 'Activo', 'Proveedores']

    def get_queryset(self):
        qs = Product.objects.select_related('brand', 'group').prefetch_related('suppliers').all()
        g = self.request.GET

        # --- Filtro por nombre (texto parcial, case-insensitive) ---
        name = g.get('name', '').strip()
        if name:
            qs = qs.filter(name__icontains=name)

        # --- Filtro por marca (FK — select) ---
        brand = g.get('brand', '').strip()
        if brand:
            qs = qs.filter(brand_id=brand)

        # --- Filtro por grupo (FK — select) ---
        group = g.get('group', '').strip()
        if group:
            qs = qs.filter(group_id=group)

        # --- Filtro por proveedor (M2M — select) ---
        supplier = g.get('supplier', '').strip()
        if supplier:
            qs = qs.filter(suppliers__id=supplier)

        # --- Filtro por precio mínimo (decimal) ---
        price_min = g.get('price_min', '').strip()
        if price_min:
            try:
                qs = qs.filter(unit_price__gte=price_min)
            except (ValueError, TypeError):
                pass

        # --- Filtro por precio máximo (decimal) ---
        price_max = g.get('price_max', '').strip()
        if price_max:
            try:
                qs = qs.filter(unit_price__lte=price_max)
            except (ValueError, TypeError):
                pass

        # --- Filtro por stock mínimo (entero) ---
        stock_min = g.get('stock_min', '').strip()
        if stock_min:
            try:
                qs = qs.filter(stock__gte=int(stock_min))
            except (ValueError, TypeError):
                pass

        # --- Filtro por stock máximo (entero) ---
        stock_max = g.get('stock_max', '').strip()
        if stock_max:
            try:
                qs = qs.filter(stock__lte=int(stock_max))
            except (ValueError, TypeError):
                pass

        # --- Filtro por estado activo (boolean — select) ---
        is_active = g.get('is_active', '').strip()
        if is_active in ('true', 'false'):
            qs = qs.filter(is_active=(is_active == 'true'))

        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        g = self.request.GET
        # Listas para los <select> de los filtros
        context['brands'] = Brand.objects.filter(is_active=True).order_by('name')
        context['groups'] = ProductGroup.objects.filter(is_active=True).order_by('name')
        context['suppliers'] = Supplier.objects.filter(is_active=True).order_by('name')
        # Preservar los valores actuales de los filtros en el template
        context['current_filters'] = {
            'name': g.get('name', ''),
            'brand': g.get('brand', ''),
            'group': g.get('group', ''),
            'supplier': g.get('supplier', ''),
            'price_min': g.get('price_min', ''),
            'price_max': g.get('price_max', ''),
            'stock_min': g.get('stock_min', ''),
            'stock_max': g.get('stock_max', ''),
            'is_active': g.get('is_active', ''),
        }
        # Query string sin "page" para usar en la paginación
        query_params = g.copy()
        query_params.pop('page', None)
        context['query_string'] = query_params.urlencode()
        return context
    
class ProductCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')
    permission_required = 'billing.add_product'
    permission_redirect_url = '/products/'

class ProductUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')
    permission_required = 'billing.change_product'
    permission_redirect_url = '/products/'

# === CUSTOMER (CBV) ===
class CustomerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Customer; template_name = 'billing/customer_list.html'; context_object_name = 'items'
    permission_required = 'billing.view_customer'; permission_redirect_url = '/'
class CustomerCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Customer; fields = ['dni','document_type','business_name','first_name','last_name','email','phone','address','is_active']; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
    permission_required = 'billing.add_customer'; permission_redirect_url = '/customers/'
class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Customer; fields = ['dni','document_type','business_name','first_name','last_name','email','phone','address','is_active']; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
    permission_required = 'billing.change_customer'; permission_redirect_url = '/customers/'

# === INVOICE (CBV) ===
@login_required
@permission_required_redirect('billing.view_invoice', redirect_to='billing:home')
def invoice_list(request):
    """Lista todas las facturas con sus totales."""
    invoices = Invoice.objects.select_related('customer').all()
    return render(request, 'billing/invoice_list.html', {'items': invoices})


@login_required
@permission_required_redirect('billing.add_invoice', redirect_to='billing:invoice_list')
def invoice_create(request):
    """Crea factura con sus líneas de detalle."""
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceDetailFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            # Guardar factura (sin commit para asignar totales)
            invoice = form.save(commit=False)
            invoice.save()

            # Asignar la factura al formset y guardar detalles
            formset.instance = invoice
            details = formset.save()

            # Actualizar stock restando la cantidad vendida
            for d in details:
                Product.objects.filter(pk=d.product_id).update(stock=F('stock') - d.quantity)

            # Calcular totales
            subtotal = sum(d.subtotal for d in invoice.details.all())
            invoice.subtotal = subtotal
            invoice.tax = subtotal * Decimal('0.15')  # IVA 15%
            invoice.total = invoice.subtotal + invoice.tax
            invoice.save()

            messages.success(request, f'Invoice #{invoice.id} created! Total: ${invoice.total}')
            return redirect('billing:invoice_list')
    else:
        form = InvoiceForm()
        formset = InvoiceDetailFormSet()

    return render(request, 'billing/invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Invoice',
    })


@login_required
@permission_required_redirect('billing.view_invoice', redirect_to='billing:invoice_list')
def invoice_detail(request, pk):
    """Muestra el detalle completo de una factura."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer')
                    .prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})


@login_required
@permission_required_redirect('billing.delete_invoice', redirect_to='billing:invoice_list')
def invoice_delete(request, pk):
    """Elimina una factura y todos sus detalles (CASCADE)."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        invoice_id = invoice.id
        invoice.delete()
        messages.success(request, f'Invoice #{invoice_id} deleted!')
        return redirect('billing:invoice_list')
    return render(request, 'billing/invoice_confirm_delete.html', {'object': invoice})


# === EXPORT TEMPORAL: respaldo de datos para migracion a Postgres ===
# TODO: eliminar esta vista una vez completada la migracion de base de datos.
@login_required
@user_passes_test(lambda u: u.is_superuser)
def export_data_backup(request):
    from django.core.management import call_command
    from django.http import HttpResponse
    import io

    buffer = io.StringIO()
    call_command(
        'dumpdata',
        natural_foreign=True,
        natural_primary=True,
        exclude=['contenttypes', 'auth.permission', 'admin.logentry', 'sessions.session'],
        indent=2,
        stdout=buffer,
    )
    response = HttpResponse(buffer.getvalue(), content_type='application/json')
    response['Content-Disposition'] = 'attachment; filename="backup.json"'
    return response

