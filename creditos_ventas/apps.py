from django.apps import AppConfig


class CreditosVentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'creditos_ventas'
    verbose_name = 'Créditos de Ventas'

    def ready(self):
        import creditos_ventas.signals  # noqa: F401
