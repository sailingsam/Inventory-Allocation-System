"""Concurrency safety: simultaneous allocation runs must not oversell stock.

Uses TransactionTestCase (real commits, no per-test transaction wrapping) so that the worker
threads see each other's committed data — and real PostgreSQL row/advisory locks. On SQLite
`select_for_update`/advisory locks are no-ops, so this test is skipped there.
"""

import threading
from datetime import timezone as dt_timezone

import pytest
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.allocation.services import run_allocation
from apps.inventory.models import SKU
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order


@pytest.mark.postgres
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="requires PostgreSQL row-level locking"
)
class ConcurrentAllocationTests(TransactionTestCase):
    def test_two_concurrent_runs_do_not_oversell(self):
        customer = User.objects.create_user(
            email="c@x.com", password="StrongPass123", role=Role.CUSTOMER
        )
        sku = SKU.objects.create(code="SKU-A", name="A", available_quantity=10)
        # Two orders, each wanting the ENTIRE stock. Only one can win.
        for day in (1, 2):
            create_order(
                customer=customer,
                lines=[(sku, 10)],
                order_date=timezone.datetime(2026, 4, day, 9, 0, tzinfo=dt_timezone.utc),
            )

        # Fire two allocation runs at the same instant.
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def worker():
            try:
                barrier.wait()
                run_allocation()
            except Exception as exc:  # capture, assert on main thread
                errors.append(exc)
            finally:
                connection.close()  # each thread uses its own DB connection

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, errors
        sku.refresh_from_db()
        # Only 10 units ever existed: exactly one order allocated, no oversell, no negative stock.
        assert sku.reserved_quantity == 10
        assert sku.available_quantity == 0
        assert Order.objects.filter(status=OrderStatus.ALLOCATED).count() == 1
        assert Order.objects.filter(status=OrderStatus.BACKORDERED).count() == 1
