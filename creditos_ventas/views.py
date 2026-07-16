from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DeleteView, DetailView, FormView, ListView, UpdateView
from django.views.generic.edit import CreateView

from billing.models import Invoice
from shared.mixins import PermissionRequiredMixin
from .forms import DefinirTipoPagoForm, PagoCuotaForm, PagoUnificadoForm
from .models import ComprobantePago, CuotaVenta, PagoCuotaVenta


# === FacturaVenta (Invoice) — CRUD básico centrado en el plan de pago ===
# Estas vistas administran el plan de pago de una Invoice ya existente
# (crédito/cuotas), así que reutilizan los permisos de billing.Invoice en
# vez de definir permisos propios para CuotaVenta/PagoCuotaVenta.

class FacturaVentaListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lista de facturas con su tipo de pago, saldo y estado. Con ?estado=PAGADA se filtra solo las canceladas."""
    model = Invoice
    template_name = 'creditos_ventas/factura_list.html'
    context_object_name = 'facturas'
    paginate_by = 15
    permission_required = 'billing.view_invoice'
    permission_redirect_url = '/'

    def get_queryset(self):
        qs = Invoice.objects.select_related('customer').order_by('-invoice_date')
        estado = self.request.GET.get('estado', '').strip()
        if estado in (Invoice.ESTADO_PENDIENTE, Invoice.ESTADO_PAGADA):
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['estado_filtro'] = self.request.GET.get('estado', '')
        return context


class FacturaVentaDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Detalle de una factura: cliente, productos facturados, cuotas y pagos."""
    model = Invoice
    template_name = 'creditos_ventas/factura_detail.html'
    context_object_name = 'factura'
    permission_required = 'billing.view_invoice'
    permission_redirect_url = '/'

    def get_queryset(self):
        return Invoice.objects.select_related('customer').prefetch_related(
            'details__product', 'cuotas__pagos',
        )


class FacturaVentaUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """
    Define (o corrige, mientras siga PENDIENTE) el tipo de pago de la factura.
    Si es CONTADO la cancela automáticamente; si es CREDITO genera las cuotas.
    Bloquea la edición si la factura ya está PAGADA.
    """
    model = Invoice
    form_class = DefinirTipoPagoForm
    template_name = 'creditos_ventas/factura_form.html'
    permission_required = 'billing.change_invoice'
    permission_redirect_url = 'creditos_ventas:factura_list'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.estado == Invoice.ESTADO_PAGADA:
            messages.error(request, 'No se puede modificar una factura que ya está PAGADA.')
            return redirect('creditos_ventas:factura_detail', pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            factura = form.save(commit=False)
            tipo_pago = form.cleaned_data['tipo_pago']

            if tipo_pago == Invoice.TIPO_PAGO_CONTADO:
                factura.marcar_como_contado()
            else:
                factura.tipo_pago = Invoice.TIPO_PAGO_CREDITO
                factura.save(update_fields=['tipo_pago'])
                CuotaVenta.generar_para_factura(factura, form.cleaned_data['numero_cuotas'])

        messages.success(self.request, f'Plan de pago definido para la Factura #{factura.pk}.')
        return redirect('creditos_ventas:factura_detail', pk=factura.pk)


class FacturaVentaDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Elimina una factura. Bloqueada si tiene cuotas (PROTECT) o ya está PAGADA."""
    model = Invoice
    template_name = 'creditos_ventas/factura_confirm_delete.html'
    success_url = reverse_lazy('creditos_ventas:factura_list')
    permission_required = 'billing.delete_invoice'
    permission_redirect_url = 'creditos_ventas:factura_list'

    def form_valid(self, form):
        if self.object.estado == Invoice.ESTADO_PAGADA:
            messages.error(self.request, 'No se puede eliminar una factura que ya está PAGADA.')
            return redirect('creditos_ventas:factura_detail', pk=self.object.pk)
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, 'No se puede eliminar: la factura tiene cuotas asociadas.')
            return redirect('creditos_ventas:factura_detail', pk=self.object.pk)


# === Generación de cuotas ===

class GenerarCuotasView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """Vista dedicada a solicitar la cantidad de cuotas y generarlas para una venta a crédito."""
    form_class = DefinirTipoPagoForm
    template_name = 'creditos_ventas/generar_cuotas_form.html'
    permission_required = 'billing.change_invoice'
    permission_redirect_url = 'creditos_ventas:factura_list'

    def dispatch(self, request, *args, **kwargs):
        self.factura = get_object_or_404(Invoice, pk=kwargs['pk'])
        if self.factura.estado == Invoice.ESTADO_PAGADA:
            messages.error(request, 'La factura ya está PAGADA.')
            return redirect('creditos_ventas:factura_detail', pk=self.factura.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.factura
        kwargs['initial'] = {'tipo_pago': Invoice.TIPO_PAGO_CREDITO}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['factura'] = self.factura
        return context

    def form_valid(self, form):
        with transaction.atomic():
            tipo_pago = form.cleaned_data['tipo_pago']
            if tipo_pago == Invoice.TIPO_PAGO_CONTADO:
                self.factura.marcar_como_contado()
            else:
                self.factura.tipo_pago = Invoice.TIPO_PAGO_CREDITO
                self.factura.save(update_fields=['tipo_pago'])
                try:
                    CuotaVenta.generar_para_factura(self.factura, form.cleaned_data['numero_cuotas'])
                except ValidationError as exc:
                    form.add_error(None, exc)
                    return self.form_invalid(form)

        messages.success(self.request, f'Cuotas generadas para la Factura #{self.factura.pk}.')
        return redirect('creditos_ventas:factura_detail', pk=self.factura.pk)


# === Cuotas ===

class CuotaVentaDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Elimina una cuota. Bloqueada si ya tiene pagos registrados (PROTECT en PagoCuotaVenta.cuota)."""
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_confirm_delete.html'
    permission_required = 'billing.delete_invoice'
    permission_redirect_url = 'creditos_ventas:factura_list'

    def get_success_url(self):
        return reverse('creditos_ventas:factura_detail', kwargs={'pk': self.object.factura_id})

    def form_valid(self, form):
        if self.object.pagos.exists():
            messages.error(self.request, 'No se puede eliminar una cuota que ya tiene pagos registrados.')
            return redirect('creditos_ventas:factura_detail', pk=self.object.factura_id)
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, 'No se puede eliminar: la cuota tiene pagos asociados.')
            return redirect('creditos_ventas:factura_detail', pk=self.object.factura_id)


# === Pagos de cuota / Comprobantes ===

class RegistrarPagoView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    Registra el abono de UNA cuota. Genera automáticamente un ComprobantePago
    (con esa única cuota) como recibo de la operación. La actualización de
    saldos de cuota/factura y el total del comprobante ocurren vía signal post_save.
    """
    model = PagoCuotaVenta
    form_class = PagoCuotaForm
    template_name = 'creditos_ventas/pago_form.html'
    permission_required = 'billing.change_invoice'
    permission_redirect_url = 'creditos_ventas:factura_list'

    def dispatch(self, request, *args, **kwargs):
        self.cuota = get_object_or_404(CuotaVenta, pk=kwargs['cuota_pk'])
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
            with transaction.atomic():
                comprobante = ComprobantePago.objects.create(cliente=self.cuota.factura.customer)
                self.object = form.save(commit=False)
                self.object.comprobante = comprobante
                self.object.save()
        except IntegrityError:
            messages.error(self.request, 'No se pudo registrar el pago debido a un conflicto de datos.')
            return self.form_invalid(form)

        messages.success(self.request, f'Pago de ${self.object.valor} registrado. Comprobante {comprobante.numero_comprobante}.')
        return redirect('creditos_ventas:comprobante_detail', pk=comprobante.pk)


class RegistrarPagoUnificadoView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """
    Permite seleccionar varias cuotas pendientes de una factura y registrarles
    un pago en una sola operación, generando UN solo ComprobantePago que agrupa
    todos los PagoCuotaVenta creados.
    """
    form_class = PagoUnificadoForm
    template_name = 'creditos_ventas/pago_unificado_form.html'
    permission_required = 'billing.change_invoice'
    permission_redirect_url = 'creditos_ventas:factura_list'

    def dispatch(self, request, *args, **kwargs):
        self.factura = get_object_or_404(Invoice, pk=kwargs['pk'])
        if not self.factura.cuotas.filter(estado=CuotaVenta.ESTADO_PENDIENTE).exists():
            messages.info(request, 'Esta factura no tiene cuotas pendientes de pago.')
            return redirect('creditos_ventas:factura_detail', pk=self.factura.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['factura'] = self.factura
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['factura'] = self.factura
        form = context['form']
        context['filas'] = [(cuota, form[f'pagar_{cuota.id}'], form[f'valor_{cuota.id}']) for cuota in form.cuotas]
        return context

    def form_valid(self, form):
        with transaction.atomic():
            comprobante = ComprobantePago.objects.create(cliente=self.factura.customer)
            for cuota, valor in form.cleaned_data['seleccionadas']:
                PagoCuotaVenta.objects.create(
                    cuota=cuota,
                    comprobante=comprobante,
                    fecha=form.cleaned_data['fecha'],
                    valor=valor,
                    observacion=form.cleaned_data.get('observacion', ''),
                )

        messages.success(
            self.request,
            f'Comprobante {comprobante.numero_comprobante} generado por ${comprobante.total_pagado}.'
        )
        return redirect('creditos_ventas:comprobante_detail', pk=comprobante.pk)


class ComprobantePagoDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Recibo/comprobante de pago: detalle de las cuotas pagadas en una misma transacción."""
    model = ComprobantePago
    template_name = 'creditos_ventas/comprobante_detail.html'
    context_object_name = 'comprobante'
    permission_required = 'billing.view_invoice'
    permission_redirect_url = 'creditos_ventas:factura_list'

    def get_queryset(self):
        return ComprobantePago.objects.select_related('cliente').prefetch_related('pagos__cuota__factura')


# === Exportación a PDF ===

class FacturaVentaPagosPdfView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    Único botón de exportación dentro de la factura a crédito: genera un PDF
    con los pagos de las cuotas que YA están en estado PAGADA (ignora cuotas
    pendientes o con abonos parciales todavía no completados).
    """
    permission_required = 'billing.view_invoice'
    permission_redirect_url = 'creditos_ventas:factura_list'

    def get(self, request, pk):
        factura = get_object_or_404(Invoice.objects.select_related('customer'), pk=pk)
        if factura.tipo_pago != Invoice.TIPO_PAGO_CREDITO:
            messages.error(request, 'La exportación de pagos a PDF aplica solo a ventas a crédito.')
            return redirect('creditos_ventas:factura_detail', pk=pk)

        pagos = (
            PagoCuotaVenta.objects.filter(cuota__factura=factura, cuota__estado=CuotaVenta.ESTADO_PAGADA)
            .select_related('cuota', 'comprobante')
            .order_by('cuota__numero', 'fecha')
        )
        if not pagos.exists():
            messages.info(request, 'Esta factura todavía no tiene cuotas en estado PAGADA.')
            return redirect('creditos_ventas:factura_detail', pk=pk)

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="factura_{factura.id}_pagos_pagados.pdf"'

        doc = SimpleDocTemplate(
            response, pagesize=letter,
            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], textColor=colors.HexColor('#212529'))
        subtitle_style = ParagraphStyle('SubtitleStyle', parent=styles['Normal'], textColor=colors.HexColor('#6C757D'))

        story = [
            Paragraph(f'Pagos de cuotas PAGADAS - Factura #{factura.id}', title_style),
            Paragraph(f'Generado el {timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M")}', subtitle_style),
            Spacer(1, 16),
            Paragraph(f'<b>Cliente:</b> {factura.customer.full_name} (DNI/RUC: {factura.customer.dni})', styles['Normal']),
            Paragraph(f'<b>Total de la factura:</b> ${factura.total} &nbsp;&nbsp; <b>Saldo pendiente:</b> ${factura.saldo}', styles['Normal']),
            Spacer(1, 16),
        ]

        pago_rows = [['Comprobante', 'Cuota', 'Fecha de pago', 'Valor', 'Observación']]
        total_pagado = Decimal('0.00')
        for pago in pagos:
            pago_rows.append([
                pago.comprobante.numero_comprobante if pago.comprobante_id else '—',
                pago.cuota.numero,
                pago.fecha.strftime('%d/%m/%Y'),
                f'${pago.valor}',
                pago.observacion or '—',
            ])
            total_pagado += pago.valor
        pago_rows.append(['', '', '', 'TOTAL', f'${total_pagado}'])

        tabla_pagos = Table(pago_rows, colWidths=[100, 50, 90, 90, 130])
        tabla_pagos.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#343A40')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#DEE2E6')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFF3CD')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F8F9FA')]),
        ]))
        story.append(tabla_pagos)

        doc.build(story)
        return response
