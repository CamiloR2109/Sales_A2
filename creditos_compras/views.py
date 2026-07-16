from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import DeleteView, DetailView, FormView, ListView, UpdateView

from purchasing.models import Purchase
from shared.mixins import PermissionRequiredMixin
from .forms import DefinirTipoPagoCompraForm, PagoCuotaCompraForm
from .models import CuotaCompra, PagoCuotaCompra


# === Compra (Purchase) — CRUD básico centrado en el plan de pago ===
# Estas vistas administran el plan de pago de una Purchase ya existente
# (crédito/cuotas), así que reutilizan los permisos de purchasing.Purchase
# en vez de definir permisos propios para CuotaCompra/PagoCuotaCompra.

class CompraListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista de compras con su tipo de pago, saldo y estado. Con ?estado=PAGADA se filtra."""
    model = Purchase
    template_name = 'creditos_compras/compra_list.html'
    context_object_name = 'compras'
    paginate_by = 15
    permission_required = 'purchasing.view_purchase'
    permission_redirect_url = '/'

    def get_queryset(self):
        qs = Purchase.objects.select_related('supplier').order_by('-purchase_date')
        estado = self.request.GET.get('estado', '').strip()
        if estado in (Purchase.ESTADO_PENDIENTE, Purchase.ESTADO_PAGADA):
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['estado_filtro'] = self.request.GET.get('estado', '')
        return context


class CompraDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Detalle de una compra: proveedor, productos y cuotas."""
    model = Purchase
    template_name = 'creditos_compras/compra_detail.html'
    context_object_name = 'compra'
    permission_required = 'purchasing.view_purchase'
    permission_redirect_url = '/'

    def get_queryset(self):
        return Purchase.objects.select_related('supplier').prefetch_related(
            'details__product', 'cuotas__pagos',
        )


class DefinirTipoPagoCompraView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """
    Vista de "Registro de tipo de pago": define si la compra es CONTADO o
    CREDITO. Si es CONTADO la cancela automáticamente; si es CREDITO, además
    genera las cuotas (vista de "generación de cuotas" combinada aquí).
    Bloquea la edición si la compra ya está PAGADA.
    """
    model = Purchase
    form_class = DefinirTipoPagoCompraForm
    template_name = 'creditos_compras/compra_form.html'
    permission_required = 'purchasing.change_purchase'
    permission_redirect_url = 'purchasing:purchase_list'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.estado == Purchase.ESTADO_PAGADA:
            messages.error(request, 'No se puede modificar una compra que ya está PAGADA.')
            return redirect('creditos_compras:compra_detail', pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        compra = form.save(commit=False)
        tipo_pago = form.cleaned_data['tipo_pago']

        if tipo_pago == Purchase.TIPO_PAGO_CONTADO:
            compra.marcar_como_contado()
        else:
            compra.tipo_pago = Purchase.TIPO_PAGO_CREDITO
            compra.save(update_fields=['tipo_pago'])
            CuotaCompra.generar_para_compra(compra, form.cleaned_data['numero_cuotas'])

        messages.success(self.request, f'Plan de pago definido para la Compra #{compra.pk}.')
        return redirect('creditos_compras:compra_detail', pk=compra.pk)


class CompraDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Elimina una compra. Bloqueada si tiene cuotas (PROTECT) o ya está PAGADA."""
    model = Purchase
    template_name = 'creditos_compras/compra_confirm_delete.html'
    success_url = reverse_lazy('creditos_compras:compra_list')
    permission_required = 'purchasing.delete_purchase'
    permission_redirect_url = 'purchasing:purchase_list'

    def form_valid(self, form):
        if self.object.estado == Purchase.ESTADO_PAGADA:
            messages.error(self.request, 'No se puede eliminar una compra que ya está PAGADA.')
            return redirect('creditos_compras:compra_detail', pk=self.object.pk)
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, 'No se puede eliminar: la compra tiene cuotas asociadas.')
            return redirect('creditos_compras:compra_detail', pk=self.object.pk)


# === Generación de cuotas (vista dedicada, además del flujo combinado de arriba) ===

class GenerarCuotasCompraView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """Vista dedicada de "generación de cuotas" para una compra a crédito ya definida."""
    form_class = DefinirTipoPagoCompraForm
    template_name = 'creditos_compras/generar_cuotas_form.html'
    permission_required = 'purchasing.change_purchase'
    permission_redirect_url = 'purchasing:purchase_list'

    def dispatch(self, request, *args, **kwargs):
        self.compra = get_object_or_404(Purchase, pk=kwargs['pk'])
        if self.compra.estado == Purchase.ESTADO_PAGADA:
            messages.error(request, 'La compra ya está PAGADA.')
            return redirect('creditos_compras:compra_detail', pk=self.compra.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.compra
        kwargs['initial'] = {'tipo_pago': Purchase.TIPO_PAGO_CREDITO}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['compra'] = self.compra
        return context

    def form_valid(self, form):
        tipo_pago = form.cleaned_data['tipo_pago']
        if tipo_pago == Purchase.TIPO_PAGO_CONTADO:
            self.compra.marcar_como_contado()
        else:
            self.compra.tipo_pago = Purchase.TIPO_PAGO_CREDITO
            self.compra.save(update_fields=['tipo_pago'])
            try:
                CuotaCompra.generar_para_compra(self.compra, form.cleaned_data['numero_cuotas'])
            except ValidationError as exc:
                form.add_error(None, exc)
                return self.form_invalid(form)

        messages.success(self.request, f'Cuotas generadas para la Compra #{self.compra.pk}.')
        return redirect('creditos_compras:compra_detail', pk=self.compra.pk)


# === Cuotas ===

class CuotaCompraListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Vista de "lista de cuotas" de una compra específica."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_list.html'
    context_object_name = 'cuotas'
    permission_required = 'purchasing.view_purchase'
    permission_redirect_url = 'purchasing:purchase_list'

    def dispatch(self, request, *args, **kwargs):
        self.compra = get_object_or_404(Purchase, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.compra.cuotas.prefetch_related('pagos').order_by('numero')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['compra'] = self.compra
        return context


class CuotasPendientesListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Vista de "consulta de cuotas pendientes": todas las cuotas PENDIENTE de todas las compras."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuotas_pendientes_list.html'
    context_object_name = 'cuotas'
    paginate_by = 20
    permission_required = 'purchasing.view_purchase'
    permission_redirect_url = 'purchasing:purchase_list'

    def get_queryset(self):
        return (
            CuotaCompra.objects.filter(estado=CuotaCompra.ESTADO_PENDIENTE)
            .select_related('compra', 'compra__supplier')
            .order_by('fecha_vencimiento')
        )


class CuotaCompraDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Elimina una cuota. Bloqueada si ya tiene pagos registrados (PROTECT en PagoCuotaCompra.cuota)."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_confirm_delete.html'
    permission_required = 'purchasing.delete_purchase'
    permission_redirect_url = 'purchasing:purchase_list'

    def get_success_url(self):
        return reverse('creditos_compras:compra_detail', kwargs={'pk': self.object.compra_id})

    def form_valid(self, form):
        if self.object.pagos.exists():
            messages.error(self.request, 'No se puede eliminar una cuota que ya tiene pagos registrados.')
            return redirect('creditos_compras:compra_detail', pk=self.object.compra_id)
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, 'No se puede eliminar: la cuota tiene pagos asociados.')
            return redirect('creditos_compras:compra_detail', pk=self.object.compra_id)


# === Pagos ===

class RegistrarPagoCompraView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """
    Vista de "registro de pagos": la creación real ocurre en
    CuotaCompra.registrar_pago(), que centraliza la lógica de negocio y el
    control de concurrencia (select_for_update) en el modelo.
    """
    form_class = PagoCuotaCompraForm
    template_name = 'creditos_compras/pago_form.html'
    permission_required = 'purchasing.change_purchase'
    permission_redirect_url = 'purchasing:purchase_list'

    def dispatch(self, request, *args, **kwargs):
        self.cuota = get_object_or_404(CuotaCompra, pk=kwargs['cuota_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['cuota'] = self.cuota
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cuota'] = self.cuota
        return context

    def form_valid(self, form):
        try:
            pago = CuotaCompra.registrar_pago(
                cuota_id=self.cuota.pk,
                fecha=form.cleaned_data['fecha'],
                valor=form.cleaned_data['valor'],
                observacion=form.cleaned_data.get('observacion', ''),
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        messages.success(self.request, f'Pago de ${pago.valor} registrado en la cuota #{self.cuota.numero}.')
        return redirect('creditos_compras:historial_pagos', pk=self.cuota.pk)


class HistorialPagosCompraView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Vista de "historial de pagos" de una cuota específica."""
    model = CuotaCompra
    template_name = 'creditos_compras/historial_pagos.html'
    context_object_name = 'cuota'
    permission_required = 'purchasing.view_purchase'
    permission_redirect_url = 'purchasing:purchase_list'

    def get_queryset(self):
        return CuotaCompra.objects.select_related('compra').prefetch_related('pagos')
