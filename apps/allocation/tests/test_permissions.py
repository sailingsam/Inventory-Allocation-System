"""Authorization for allocation endpoints (the FCFS behaviour itself is tested in Stage 6,
after the engine is implemented)."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.allocation.models import AllocationRun

pytestmark = pytest.mark.django_db


def _client(role):
    user = User.objects.create_user(email=f"{role.lower()}@x.com", password="StrongPass123", role=role)
    c = APIClient()
    c.force_authenticate(user=user)
    return c, user


def test_run_requires_auth():
    assert APIClient().post("/api/allocation/run/").status_code == 401


def test_customer_cannot_run_allocation():
    customer, _ = _client(Role.CUSTOMER)
    assert customer.post("/api/allocation/run/").status_code == 403


def test_customer_cannot_view_runs():
    customer, _ = _client(Role.CUSTOMER)
    assert customer.get("/api/allocation/runs/").status_code == 403


def test_operator_can_view_audit_log():
    operator, op = _client(Role.WAREHOUSE_OPERATOR)
    AllocationRun.objects.create(actor=op, orders_processed=3, orders_allocated=2, orders_backordered=1)
    resp = operator.get("/api/allocation/runs/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["orders_allocated"] == 2
