from rest_framework.permissions import BasePermission,SAFE_METHODS
from django.conf import settings

STAFF_ROLES={'administrator','operator','analyst'}

class IsStaffReader(BasePermission):
    def has_permission(self,request,view):
        return bool(request.user.is_authenticated and (request.user.is_superuser or request.user.role in STAFF_ROLES))

class IsOperator(BasePermission):
    def has_permission(self,request,view):
        return bool(request.user.is_authenticated and (request.user.is_superuser or request.user.role in {'administrator','operator'}))

class IsAdministrator(BasePermission):
    def has_permission(self,request,view):
        return bool(request.user.is_authenticated and (request.user.is_superuser or request.user.role=='administrator'))

class IsStaff(IsStaffReader):
    """Compatibility name for read-only reporting/import views; mutation needs IsOperator."""
    pass
