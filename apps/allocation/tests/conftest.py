from datetime import timezone as dt_timezone

import pytest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.inventory.models import SKU
from apps.orders.services import create_order


@pytest.fixture
def customer(db):
    return User.objects.create_user(email="c@x.com", password="StrongPass123", role=Role.CUSTOMER)


@pytest.fixture
def make_sku(db):
    def _make(code="SKU-A", available=12, name="Widget"):
        return SKU.objects.create(code=code, name=name, available_quantity=available)

    return _make


@pytest.fixture
def make_order(customer):
    """Create a PENDING order with an explicit order_date (day-of-April for readability)."""

    def _make(lines, april_day=1):
        order_date = timezone.datetime(2026, 4, april_day, 9, 0, tzinfo=dt_timezone.utc)
        return create_order(customer=customer, lines=lines, order_date=order_date)

    return _make
