"""Authorization: role gates on the admin user-management endpoint.

401 for unauthenticated, 403 for authenticated-but-wrong-role.
"""

import pytest

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db


def test_user_management_requires_auth(api):
    assert api.get("/api/users/").status_code == 401


def test_customer_cannot_manage_users(auth_client):
    api, _ = auth_client(role=Role.CUSTOMER)
    assert api.get("/api/users/").status_code == 403


def test_operator_cannot_register_admins(auth_client):
    """An Operator must not be able to create users/admins (explicitly tested in the brief)."""
    api, _ = auth_client(role=Role.WAREHOUSE_OPERATOR)
    resp = api.post(
        "/api/users/",
        {"email": "evil-admin@example.com", "password": "StrongPass123", "role": Role.ADMIN},
        format="json",
    )
    assert resp.status_code == 403
    assert not User.objects.filter(email="evil-admin@example.com").exists()


def test_admin_can_create_operator(auth_client):
    api, _ = auth_client(role=Role.ADMIN)
    resp = api.post(
        "/api/users/",
        {"email": "op@example.com", "password": "StrongPass123", "role": Role.WAREHOUSE_OPERATOR},
        format="json",
    )
    assert resp.status_code == 201
    assert User.objects.get(email="op@example.com").role == Role.WAREHOUSE_OPERATOR


def test_superuser_passes_role_gate(api, make_user):
    su = make_user(email="root@example.com", role=Role.ADMIN, is_superuser=True, is_staff=True)
    api.force_authenticate(user=su)
    assert api.get("/api/users/").status_code == 200
