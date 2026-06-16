"""SKU endpoints + ledgered stock service."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.inventory.models import SKU, StockLedger, StockReason
from apps.inventory.services import InsufficientStock, adjust_stock

pytestmark = pytest.mark.django_db


@pytest.fixture
def api():
    return APIClient()


def _client(role):
    user = User.objects.create_user(email=f"{role.lower()}@x.com", password="StrongPass123", role=role)
    c = APIClient()
    c.force_authenticate(user=user)
    return c, user


def test_list_skus_any_authenticated(api):
    SKU.objects.create(code="SKU-A", name="A", available_quantity=12)
    customer, _ = _client(Role.CUSTOMER)
    resp = customer.get("/api/skus/")
    assert resp.status_code == 200
    assert resp.data["results"][0]["code"] == "SKU-A"


def test_list_skus_requires_auth(api):
    assert api.get("/api/skus/").status_code == 401


def test_customer_cannot_create_sku():
    customer, _ = _client(Role.CUSTOMER)
    resp = customer.post("/api/skus/", {"code": "SKU-B", "name": "B"}, format="json")
    assert resp.status_code == 403


def test_operator_can_create_sku():
    operator, _ = _client(Role.WAREHOUSE_OPERATOR)
    resp = operator.post(
        "/api/skus/", {"code": "SKU-B", "name": "B", "available_quantity": 5}, format="json"
    )
    assert resp.status_code == 201
    assert SKU.objects.get(code="SKU-B").available_quantity == 5


def test_reserved_quantity_is_read_only_on_create():
    operator, _ = _client(Role.WAREHOUSE_OPERATOR)
    operator.post(
        "/api/skus/",
        {"code": "SKU-C", "name": "C", "available_quantity": 5, "reserved_quantity": 99},
        format="json",
    )
    assert SKU.objects.get(code="SKU-C").reserved_quantity == 0


def test_stock_adjust_writes_ledger():
    operator, user = _client(Role.WAREHOUSE_OPERATOR)
    sku = SKU.objects.create(code="SKU-D", name="D", available_quantity=10)
    resp = operator.patch(
        f"/api/skus/{sku.id}/stock/",
        {"available_delta": 40, "reason": StockReason.RESTOCK},
        format="json",
    )
    assert resp.status_code == 200
    sku.refresh_from_db()
    assert sku.available_quantity == 50
    entry = StockLedger.objects.get(sku=sku)
    assert entry.available_change == 40
    assert entry.available_after == 50
    assert entry.actor == user


def test_customer_cannot_adjust_stock():
    customer, _ = _client(Role.CUSTOMER)
    sku = SKU.objects.create(code="SKU-E", name="E", available_quantity=10)
    resp = customer.patch(f"/api/skus/{sku.id}/stock/", {"available_delta": 5}, format="json")
    assert resp.status_code == 403


def test_negative_adjustment_below_zero_rejected():
    operator, _ = _client(Role.WAREHOUSE_OPERATOR)
    sku = SKU.objects.create(code="SKU-F", name="F", available_quantity=3)
    resp = operator.patch(f"/api/skus/{sku.id}/stock/", {"available_delta": -5}, format="json")
    assert resp.status_code == 400
    sku.refresh_from_db()
    assert sku.available_quantity == 3  # unchanged


def test_service_move_stock_guards_non_negative():
    sku = SKU.objects.create(code="SKU-G", name="G", available_quantity=2)
    with pytest.raises(InsufficientStock):
        adjust_stock(sku_id=sku.id, available_delta=-10)
