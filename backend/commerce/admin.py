from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import transaction
from .models import User,Product,SKU,Order,OrderLine,Shipment,Payment,PaymentSettlement,ReturnRequest,Refund,StockMovement,AuditEvent,CompanySettings,DeliveryZone
from .services import audit

class AuditedAdminMixin:
    @transaction.atomic
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        audit(request.user,'admin_updated' if change else 'admin_created',obj._meta.model_name,obj.pk)
    @transaction.atomic
    def delete_model(self,request,obj):
        reference=obj.pk
        super().delete_model(request,obj)
        audit(request.user,'admin_deleted',obj._meta.model_name,reference)
    @transaction.atomic
    def delete_queryset(self,request,queryset):
        references=list(queryset.values_list('pk',flat=True))
        super().delete_queryset(request,queryset)
        for reference in references:
            audit(request.user,'admin_deleted',queryset.model._meta.model_name,reference)

@admin.register(User)
class CommerceUserAdmin(AuditedAdminMixin,UserAdmin):
    fieldsets=UserAdmin.fieldsets+(('Commerce',{'fields':('role',)}),)

class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

for model in [Order,OrderLine,Shipment,Payment,PaymentSettlement,ReturnRequest,Refund,StockMovement,AuditEvent,SKU]:
    admin.site.register(model,ReadOnlyAdmin)
class AuditedAdmin(AuditedAdminMixin,admin.ModelAdmin):
    pass

admin.site.register(Product,AuditedAdmin)
@admin.register(CompanySettings)
class CompanySettingsAdmin(AuditedAdmin):
    readonly_fields=('currency','timezone')
    def has_add_permission(self,request):
        return not CompanySettings.objects.exists() and super().has_add_permission(request)
admin.site.register(DeliveryZone,AuditedAdmin)
