from rest_framework.permissions import BasePermission
from users.models import User


class IsDoctor(BasePermission):
    message = 'Доступ разрешён только врачам.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.DOCTOR
        )
