"""Order create/list/retrieve + cancel/fulfill lifecycle and authorization."""

import pytest
from django.utils import timezone

from apps.inventory.models import SKU, StockReason
from apps.orders.models import Order, OrderStatus

pytestmark = pytest.mark.django_db


# ---- creation ------------------------------------------------------------------------

def test_customer_creates_order(client_for, customer, sku):
    c = client_for(customer)
    resp = c.post("/api/orders/", {"lines": [{"sku": sku.id, "quantity": 3}]}, format="json")
    assert resp.status_code == 201
    assert resp.data["status"] == OrderStatus.PENDING
    assert resp.data["lines"][0]["quantity"] == 3
    # creating an order does NOT reserve stock
    sku.refresh_from_db()
    assert sku.available_quantity == 12 and sku.reserved_quantity == 0


def test_operator_cannot_create_order(client_for, operator, sku):
    resp = client_for(operator).post(
        "/api/orders/", {"lines": [{"sku": sku.id, "quantity": 1}]}, format="json"
    )
    assert resp.status_code == 403


def test_order_date_is_not_client_settable(client_for, customer, sku):
    """Customer-supplied order_date is ignored — it is server-set (immutable via API)."""
    backdate = "2000-01-01T00:00:00Z"
    resp = client_for(customer).post(
        "/api/orders/",
        {"lines": [{"sku": sku.id, "quantity": 1}], "order_date": backdate},
        format="json",
    )
    assert resp.status_code == 201
    order = Order.objects.get(pk=resp.data["id"])
    assert order.order_date.year == timezone.now().year  # not 2000


def test_empty_order_rejected(client_for, customer):
    resp = client_for(customer).post("/api/orders/", {"lines": []}, format="json")
    assert resp.status_code == 400


# ---- visibility / authorization ------------------------------------------------------

def test_customer_sees_only_own_orders(client_for, customer, make_user, sku):
    other = make_user("other@x.com")
    Order.objects.create(customer=other)
    own = Order.objects.create(customer=customer)
    resp = client_for(customer).get("/api/orders/")
    ids = [o["id"] for o in resp.data["results"]]
    assert own.id in ids and len(ids) == 1


def test_customer_cannot_retrieve_others_order(client_for, customer, make_user):
    other = make_user("other2@x.com")
    o = Order.objects.create(customer=other)
    assert client_for(customer).get(f"/api/orders/{o.id}/").status_code == 404


def test_operator_sees_all_orders(client_for, operator, customer):
    Order.objects.create(customer=customer)
    resp = client_for(operator).get("/api/orders/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1


# ---- cancel --------------------------------------------------------------------------

def test_customer_cancels_own_pending_order(client_for, customer, sku):
    order = Order.objects.create(customer=customer)
    resp = client_for(customer).post(f"/api/orders/{order.id}/cancel/")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED


def test_customer_cannot_cancel_allocated_order(client_for, customer, allocated_order):
    resp = client_for(customer).post(f"/api/orders/{allocated_order.id}/cancel/")
    assert resp.status_code == 403
    allocated_order.refresh_from_db()
    assert allocated_order.status == OrderStatus.ALLOCATED


def test_operator_cancel_allocated_releases_stock(client_for, operator, allocated_order, sku):
    sku.refresh_from_db()
    assert sku.available_quantity == 7 and sku.reserved_quantity == 5  # reserved by fixture
    resp = client_for(operator).post(f"/api/orders/{allocated_order.id}/cancel/")
    assert resp.status_code == 200
    sku.refresh_from_db()
    assert sku.available_quantity == 12 and sku.reserved_quantity == 0  # released
    # a CANCELLATION ledger row was written
    assert allocated_order.ledger_entries.filter(reason=StockReason.CANCELLATION).exists()


def test_customer_can_cancel_own_backordered_order(client_for, customer, sku):
    """A backordered order is just waiting for stock — the customer may cancel it."""
    order = Order.objects.create(customer=customer, status=OrderStatus.BACKORDERED)
    resp = client_for(customer).post(f"/api/orders/{order.id}/cancel/")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED


def test_cannot_cancel_fulfilled_order(client_for, operator, allocated_order):
    allocated_order.status = OrderStatus.FULFILLED
    allocated_order.save(update_fields=["status"])
    resp = client_for(operator).post(f"/api/orders/{allocated_order.id}/cancel/")
    assert resp.status_code == 409


# ---- fulfill -------------------------------------------------------------------------

def test_operator_fulfills_allocated_order(client_for, operator, allocated_order, sku):
    resp = client_for(operator).post(f"/api/orders/{allocated_order.id}/fulfill/")
    assert resp.status_code == 200
    allocated_order.refresh_from_db()
    assert allocated_order.status == OrderStatus.FULFILLED
    assert allocated_order.fulfilled_at is not None
    sku.refresh_from_db()
    # reserved removed; available stays where allocation left it
    assert sku.reserved_quantity == 0 and sku.available_quantity == 7


def test_double_fulfillment_rejected(client_for, operator, allocated_order):
    first = client_for(operator).post(f"/api/orders/{allocated_order.id}/fulfill/")
    assert first.status_code == 200
    second = client_for(operator).post(f"/api/orders/{allocated_order.id}/fulfill/")
    assert second.status_code == 409


def test_customer_cannot_fulfill(client_for, customer, allocated_order):
    assert client_for(customer).post(f"/api/orders/{allocated_order.id}/fulfill/").status_code == 403


def test_pending_order_cannot_be_fulfilled(client_for, operator, customer, sku):
    order = Order.objects.create(customer=customer)
    assert client_for(operator).post(f"/api/orders/{order.id}/fulfill/").status_code == 409
