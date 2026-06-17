"""FCFS allocation engine correctness + edge cases."""

from datetime import timezone as dt_timezone

import pytest
from django.utils import timezone

from apps.inventory.models import SKU, StockLedger, StockReason
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order
from apps.allocation.services import run_allocation

pytestmark = pytest.mark.django_db


def test_worked_example(make_sku, make_order):
    """The assignment's worked example: SKU-A=12, orders 5,10,4,4,3,... across Apr 1..n."""
    sku = make_sku(available=12)
    qtys = [5, 10, 4, 4, 3]
    orders = [make_order([(sku, q)], april_day=i + 1) for i, q in enumerate(qtys)]

    run_allocation()
    for o in orders:
        o.refresh_from_db()

    outcomes = [o.status for o in orders]
    assert outcomes == [
        OrderStatus.ALLOCATED,    # 5  -> 12->7
        OrderStatus.BACKORDERED,  # 10 -> needs 10, only 7
        OrderStatus.ALLOCATED,    # 4  -> 7->3
        OrderStatus.BACKORDERED,  # 4  -> needs 4, only 3
        OrderStatus.ALLOCATED,    # 3  -> 3->0
    ]
    sku.refresh_from_db()
    assert sku.available_quantity == 0 and sku.reserved_quantity == 12


def test_backdated_order_date_wins_over_created_at(make_sku, customer):
    """FCFS priority is order_date, NOT insertion order. An order created later but dated earlier
    must win when stock is scarce."""
    sku = make_sku(available=10)

    # Created FIRST, but dated LATER (Apr 5).
    later = create_order(
        customer=customer, lines=[(sku, 10)],
        order_date=timezone.datetime(2026, 4, 5, 9, 0, tzinfo=dt_timezone.utc),
    )
    # Created SECOND, but dated EARLIER (Apr 1) -> should be served first.
    earlier = create_order(
        customer=customer, lines=[(sku, 10)],
        order_date=timezone.datetime(2026, 4, 1, 9, 0, tzinfo=dt_timezone.utc),
    )

    run_allocation()
    earlier.refresh_from_db()
    later.refresh_from_db()

    assert earlier.status == OrderStatus.ALLOCATED
    assert later.status == OrderStatus.BACKORDERED


def test_created_at_breaks_ties_on_equal_order_date(make_sku, customer):
    same_date = timezone.datetime(2026, 4, 1, 9, 0, tzinfo=dt_timezone.utc)
    sku = make_sku(available=10)
    first = create_order(customer=customer, lines=[(sku, 10)], order_date=same_date)
    second = create_order(customer=customer, lines=[(sku, 10)], order_date=same_date)

    run_allocation()
    first.refresh_from_db()
    second.refresh_from_db()

    assert first.status == OrderStatus.ALLOCATED   # created first
    assert second.status == OrderStatus.BACKORDERED


def test_shortage_skips_big_order_but_allocates_later_smaller(make_sku, make_order):
    """Core FCFS edge case: a too-big order is skipped, but a later smaller order still fits."""
    sku = make_sku(available=12)
    big = make_order([(sku, 100)], april_day=1)    # can never fit
    small = make_order([(sku, 5)], april_day=2)    # fits in remaining stock

    run_allocation()
    big.refresh_from_db()
    small.refresh_from_db()

    assert big.status == OrderStatus.BACKORDERED
    assert small.status == OrderStatus.ALLOCATED
    sku.refresh_from_db()
    assert sku.available_quantity == 7


def test_no_partial_allocation_across_multiple_lines(make_sku, customer):
    """An order with one satisfiable line and one short line must allocate NOTHING."""
    x = make_sku(code="SKU-X", available=5)
    y = make_sku(code="SKU-Y", available=0)
    order = create_order(
        customer=customer, lines=[(x, 3), (y, 1)],
        order_date=timezone.datetime(2026, 4, 1, 9, 0, tzinfo=dt_timezone.utc),
    )

    run_allocation()
    order.refresh_from_db()

    assert order.status == OrderStatus.BACKORDERED
    x.refresh_from_db()
    assert x.available_quantity == 5 and x.reserved_quantity == 0  # untouched, no partial reserve


def test_backorder_false_leaves_order_pending(make_sku, make_order):
    sku = make_sku(available=1)
    order = make_order([(sku, 5)], april_day=1)

    run_allocation(backorder_on_shortage=False)
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING  # left for a later run to retry


def test_allocation_writes_ledger_linked_to_order(make_sku, make_order):
    sku = make_sku(available=12)
    order = make_order([(sku, 5)], april_day=1)

    run_allocation()
    entry = StockLedger.objects.get(order=order, reason=StockReason.ALLOCATION)
    assert entry.available_change == -5 and entry.reserved_change == 5
    assert entry.available_after == 7


def test_backordered_order_is_retried_after_restock(make_sku, make_order):
    """A backordered order must be re-checked on the next run and filled once stock arrives."""
    sku = make_sku(available=0)
    order = make_order([(sku, 5)], april_day=1)

    run_allocation()
    order.refresh_from_db()
    assert order.status == OrderStatus.BACKORDERED  # no stock yet

    # Operator restocks, then re-runs allocation.
    from apps.inventory.services import adjust_stock
    adjust_stock(sku_id=sku.id, available_delta=5)
    run_allocation()

    order.refresh_from_db()
    assert order.status == OrderStatus.ALLOCATED  # auto-filled on retry


def test_old_backordered_order_beats_newer_pending_after_restock(make_sku, make_order):
    """FCFS fairness across runs: an older backordered order is served before a newer order."""
    sku = make_sku(available=0)
    old = make_order([(sku, 5)], april_day=1)   # arrives first, gets backordered

    run_allocation()
    old.refresh_from_db()
    assert old.status == OrderStatus.BACKORDERED

    # Now a NEWER customer orders, and stock arrives enough for only ONE of them.
    newer = make_order([(sku, 5)], april_day=2)
    from apps.inventory.services import adjust_stock
    adjust_stock(sku_id=sku.id, available_delta=5)

    run_allocation()
    old.refresh_from_db()
    newer.refresh_from_db()

    assert old.status == OrderStatus.ALLOCATED      # older backordered wins
    assert newer.status == OrderStatus.BACKORDERED  # newer waits


def test_already_allocated_orders_not_reprocessed(make_sku, make_order):
    sku = make_sku(available=12)
    order = make_order([(sku, 5)], april_day=1)

    run_allocation()
    run_allocation()  # second run: nothing PENDING -> no change

    sku.refresh_from_db()
    assert sku.reserved_quantity == 5  # not double-reserved
