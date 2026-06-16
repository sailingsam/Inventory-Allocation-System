import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.inventory.models import SKU, StockReason
from apps.inventory.services import move_stock
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order


@pytest.fixture
def make_user(db):
    def _make(email, role=Role.CUSTOMER, password="StrongPass123", **kw):
        return User.objects.create_user(email=email, password=password, role=role, **kw)

    return _make


@pytest.fixture
def client_for():
    def _client(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _client


@pytest.fixture
def customer(make_user):
    return make_user("customer@x.com", role=Role.CUSTOMER)


@pytest.fixture
def operator(make_user):
    return make_user("operator@x.com", role=Role.WAREHOUSE_OPERATOR)


@pytest.fixture
def sku(db):
    return SKU.objects.create(code="SKU-A", name="Widget A", available_quantity=12)


@pytest.fixture
def allocated_order(customer, sku):
    """Build an ALLOCATED order by reserving stock directly (simulating the engine), so
    cancel/fulfill can be tested before the allocation engine exists.
    """
    order = create_order(customer=customer, lines=[(sku, 5)])
    move_stock(sku, available_delta=-5, reserved_delta=5, reason=StockReason.ALLOCATION, order=order)
    order.status = OrderStatus.ALLOCATED
    order.allocated_at = timezone.now()
    order.save(update_fields=["status", "allocated_at"])
    return order
