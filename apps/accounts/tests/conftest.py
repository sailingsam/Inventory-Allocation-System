import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make(email="u@example.com", password="StrongPass123", role=Role.CUSTOMER, **kw):
        return User.objects.create_user(email=email, password=password, role=role, **kw)

    return _make


@pytest.fixture
def auth_client(api, make_user):
    """Return a client authenticated as a user of the given role."""

    def _auth(role=Role.CUSTOMER, email=None):
        email = email or f"{role.lower()}@example.com"
        user = make_user(email=email, role=role)
        api.force_authenticate(user=user)
        return api, user

    return _auth
