"""Role-based DRF permission classes.

Convention: unauthenticated access yields 401 (JWTAuthentication sets the auth header),
authenticated-but-wrong-role yields 403. Each class only checks the role; authentication is
handled by the default IsAuthenticated-style check we fold in via `is_authenticated`.
"""

from rest_framework.permissions import BasePermission

from .models import Role


class _AuthenticatedRolePermission(BasePermission):
    """Base: require an authenticated user whose role is in `allowed_roles`.

    Superusers always pass (they represent the highest privilege).
    """

    allowed_roles: tuple[str, ...] = ()

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.role in self.allowed_roles


class IsCustomer(_AuthenticatedRolePermission):
    allowed_roles = (Role.CUSTOMER,)


class IsWarehouseOperator(_AuthenticatedRolePermission):
    allowed_roles = (Role.WAREHOUSE_OPERATOR,)


class IsAdmin(_AuthenticatedRolePermission):
    allowed_roles = (Role.ADMIN,)


class IsOperatorOrAdmin(_AuthenticatedRolePermission):
    allowed_roles = (Role.WAREHOUSE_OPERATOR, Role.ADMIN)
