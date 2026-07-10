from django.urls import path

from . import views

app_name = 'storefront'

urlpatterns = [
    path('catalog/', views.CatalogView.as_view(), name='catalog'),
    path('cart/', views.cart_detail, name='cart_detail'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'),
    path('cart/remove/<int:product_id>/', views.cart_remove, name='cart_remove'),
    path('cart/update/<int:product_id>/', views.cart_update, name='cart_update'),
]
