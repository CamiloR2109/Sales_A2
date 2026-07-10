from django.shortcuts import redirect

ALLOWED_PREFIXES = ('/shop/', '/accounts/', '/static/', '/media/')


class ClienteAccessMiddleware:
    """
    Restringe a los usuarios del rol Cliente a la tienda (/shop/) y a las
    rutas de autenticación, evitando que accedan directamente por URL a las
    vistas administrativas (productos, clientes, facturas, etc.).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user is not None
            and user.is_authenticated
            and not user.is_superuser
            and user.groups.filter(name='Cliente').exists()
            and not request.path.startswith(ALLOWED_PREFIXES)
        ):
            return redirect('storefront:catalog')
        return self.get_response(request)
