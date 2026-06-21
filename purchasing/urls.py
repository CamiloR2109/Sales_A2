from django.urls import path
from . import views
app_name = 'purchasing'
urlpatterns = [
    # Purchase
    path('invoices/', views.purchase_list, name='purchase_list'),
    path('invoices/create/', views.purchase_create, name='purchase_create'),
    path('invoices/<int:pk>/', views.purchase_detail, name='purchase_detail'),
    path('invoices/<int:pk>/delete/', views.purchase_delete, name='purchase_delete'),
]