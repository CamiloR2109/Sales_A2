from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from shared.mixins import GroupRequiredMixin
from .forms import UserRegisterForm, UserUpdateForm, GroupForm, PermissionForm

# === MIXIN BASE: SOLO ADMINISTRADOR ===
class AdminOnlyMixin(LoginRequiredMixin, GroupRequiredMixin):
    """Combina login + rol Administrador (el superusuario siempre pasa)."""
    group_required = ['Administrador']
    group_redirect_url = '/'

# === AUTENTICACIÓN (CBV) ===
class RegisterView(CreateView):
    """Registro público con selección de rol."""
    form_class = UserRegisterForm
    template_name = 'security/register.html'
    success_url = reverse_lazy('billing:home')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)   # inicia sesión automáticamente
        return response

class SecurityLoginView(LoginView):
    """Login con CBV. Reutiliza el template de la PARTE 9."""
    template_name = 'registration/login.html'

class SecurityLogoutView(LogoutView):
    """Logout con CBV. Redirige según LOGOUT_REDIRECT_URL."""
    pass

# === USUARIOS (solo Administrador) ===
class UserListView(AdminOnlyMixin, ListView):
    model = User
    template_name = 'security/user_list.html'
    context_object_name = 'items'

class UserUpdateView(AdminOnlyMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'security/user_form.html'
    success_url = reverse_lazy('security:user_list')

class UserDeleteView(AdminOnlyMixin, DeleteView):
    model = User
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:user_list')

# === ROLES / GROUP (solo Administrador) ===

# Módulos de negocio que se muestran como secciones de permisos,
# en el orden en que deben aparecer en la pantalla.
PERMISSION_MODULES = [
    ('billing', 'brand', 'Marcas'),
    ('billing', 'productgroup', 'Grupos de Producto'),
    ('billing', 'supplier', 'Proveedores'),
    ('billing', 'product', 'Productos'),
    ('billing', 'customer', 'Clientes'),
    ('billing', 'invoice', 'Facturas'),
    ('purchasing', 'purchase', 'Compras'),
    ('auth', 'user', 'Usuarios'),
    ('auth', 'group', 'Roles'),
]

# Orden y etiqueta de cada acción según el prefijo de su codename.
PERMISSION_ACTIONS = [
    ('view', 'Ver'),
    ('add', 'Crear'),
    ('change', 'Editar'),
    ('delete', 'Eliminar'),
    ('export', 'Exportar'),
    ('print', 'Imprimir'),
]

class GroupListView(AdminOnlyMixin, ListView):
    model = Group
    template_name = 'security/group_list.html'
    context_object_name = 'items'

class RolePermissionContextMixin:
    """Arma la barra lateral de roles y los permisos agrupados por módulo."""

    def get_permission_modules(self, checked_ids):
        permissions = Permission.objects.filter(
            content_type__app_label__in={app for app, _, _ in PERMISSION_MODULES},
        ).select_related('content_type')
        by_model = {}
        for perm in permissions:
            key = (perm.content_type.app_label, perm.content_type.model)
            by_model.setdefault(key, []).append(perm)

        modules = []
        for app_label, model_name, display_name in PERMISSION_MODULES:
            perms_by_action = {}
            for perm in by_model.get((app_label, model_name), []):
                for action, _ in PERMISSION_ACTIONS:
                    if perm.codename == f'{action}_{model_name}':
                        perms_by_action[action] = perm
                        break
            items = [
                {
                    'id': perms_by_action[action].id,
                    'label': label,
                    'checked': perms_by_action[action].id in checked_ids,
                }
                for action, label in PERMISSION_ACTIONS
                if action in perms_by_action
            ]
            if items:
                modules.append({'name': display_name, 'permissions': items})
        return modules

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checked_ids = set(
            self.object.permissions.values_list('id', flat=True)
        ) if getattr(self, 'object', None) else set()
        context['all_groups'] = Group.objects.order_by('name')
        context['modules'] = self.get_permission_modules(checked_ids)
        return context

class GroupCreateView(AdminOnlyMixin, RolePermissionContextMixin, CreateView):
    model = Group
    form_class = GroupForm
    template_name = 'security/group_form.html'
    success_url = reverse_lazy('security:group_list')

class GroupUpdateView(AdminOnlyMixin, RolePermissionContextMixin, UpdateView):
    model = Group
    form_class = GroupForm
    template_name = 'security/group_form.html'
    success_url = reverse_lazy('security:group_list')

class GroupDeleteView(AdminOnlyMixin, DeleteView):
    model = Group
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:group_list')

# === PERMISOS / PERMISSION (solo Administrador) ===
class PermissionListView(AdminOnlyMixin, ListView):
    model = Permission
    template_name = 'security/permission_list.html'
    context_object_name = 'items'
    queryset = Permission.objects.select_related('content_type')

class PermissionCreateView(AdminOnlyMixin, CreateView):
    model = Permission
    form_class = PermissionForm
    template_name = 'security/permission_form.html'
    success_url = reverse_lazy('security:permission_list')

class PermissionUpdateView(AdminOnlyMixin, UpdateView):
    model = Permission
    form_class = PermissionForm
    template_name = 'security/permission_form.html'
    success_url = reverse_lazy('security:permission_list')

class PermissionDeleteView(AdminOnlyMixin, DeleteView):
    model = Permission
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:permission_list')
