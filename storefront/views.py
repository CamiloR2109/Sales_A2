from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from billing.models import Product
from shared.mixins import GroupRequiredMixin

from .cart import Cart


def cliente_required(view_func):
    """Restringe una vista de función a usuarios del rol Cliente (o superuser)."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.groups.filter(name='Cliente').exists()):
            messages.error(request, 'No tienes permiso para acceder a esta sección.')
            return redirect('billing:home')
        return view_func(request, *args, **kwargs)

    return wrapper


class CatalogView(LoginRequiredMixin, GroupRequiredMixin, ListView):
    """Catálogo público de productos para el rol Cliente."""
    model = Product
    template_name = 'storefront/catalog.html'
    context_object_name = 'products'
    paginate_by = 12
    group_required = ['Cliente']

    def get_queryset(self):
        return Product.objects.filter(is_active=True, stock__gt=0).select_related('brand').order_by('name')


@cliente_required
@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    cart = Cart(request)
    cart.add(product=product, quantity=quantity)
    messages.success(request, f'"{product.name}" añadido al carrito.')
    return redirect('storefront:catalog')


@cliente_required
def cart_remove(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart = Cart(request)
    cart.remove(product)
    messages.info(request, f'"{product.name}" eliminado del carrito.')
    return redirect('storefront:cart_detail')


@cliente_required
@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1

    cart = Cart(request)
    cart.set_quantity(product, quantity)
    return redirect('storefront:cart_detail')


@cliente_required
def cart_detail(request):
    cart = Cart(request)
    return render(request, 'storefront/cart_detail.html', {'cart': cart})
