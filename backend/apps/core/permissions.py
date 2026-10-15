from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import Role


def has_any_role(*codes):
    """Permission class factory: user must hold at least one of the given role codes."""

    class HasAnyRole(BasePermission):
        message = "You do not have permission to perform this action."

        def has_permission(self, request, view):
            return bool(request.user and request.user.is_authenticated and request.user.has_role(*codes))

    return HasAnyRole


IsAdminRole = has_any_role(Role.ADMIN)


class AdminWriteAuthenticatedRead(BasePermission):
    """Reference data: any signed-in user may read, only administrators may change."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or user.has_role(Role.ADMIN)
