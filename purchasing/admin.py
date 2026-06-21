from django.contrib import admin
from .models import *

# Register your models here.
class PurchaseDetailInline(admin.TabularInline):
    model = PurchaseDetail; extra = 1
    
@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'supplier', 'document_number', 'purchase_date','total']
    inlines = [PurchaseDetailInline]