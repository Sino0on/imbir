from rest_framework.permissions import BasePermission
from users.models import User


class IsClinic(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.CLINIC
        )
