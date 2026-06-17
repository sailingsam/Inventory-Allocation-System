"""Order lifecycle services: create, cancel, fulfill.

These contain the stock *mechanics* of an order's lifecycle (reserve release on cancel, reserved
removal on fulfill) but NOT the FCFS allocation decision logic — that lives in the allocation
engine. Every stock mutation goes through `inventory.services.move_stock` under a row lock taken
in a consistent order (by SKU id) to avoid deadlocks.
"""

from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.inventory.models import SKU, StockReason
from apps.inventory.services import move_stock

from .models import Order, OrderLine, OrderStatus


class OrderError(Exception):
    """Domain error for invalid order operations (maps to HTTP 409 in the view)."""


@transaction.atomic
def create_order(*, customer, lines, order_date=None):
    """Create a PENDING order. Does NOT touch stock — reservation happens only at allocation.

    `lines` is an iterable of (sku, quantity) pairs (sku may be a SKU or its id).
    `order_date` is honoured only for seed/admin callers; the customer API never passes it.
    """
    order = Order(customer=customer, status=OrderStatus.PENDING)
    if order_date is not None:
        order.order_date = order_date
    order.save()

    OrderLine.objects.bulk_create(
        [
            OrderLine(
                order=order,
                sku_id=sku.id if isinstance(sku, SKU) else sku,
                quantity=quantity,
            )
            for sku, quantity in lines
        ]
    )
    return order


def _locked_skus_for(order):
    """Lock all SKU rows referenced by the order, ordered by id (deadlock-safe), returning a map."""
    sku_ids = sorted({line.sku_id for line in order.lines.all()})
    skus = SKU.objects.select_for_update().filter(id__in=sku_ids).order_by("id")
    return {sku.id: sku for sku in skus}


def _quantities_by_sku(order):
    totals = defaultdict(int)
    for line in order.lines.all():
        totals[line.sku_id] += line.quantity
    return totals


@transaction.atomic
def cancel_order(*, order, actor):
    """Cancel an order.

    - PENDING / BACKORDERED -> simply mark CANCELLED (no stock was reserved).
    - ALLOCATED             -> release reserved stock back to available, then mark CANCELLED.
    Any other status (FULFILLED / already CANCELLED) is a conflict.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)

    if order.status in (OrderStatus.PENDING, OrderStatus.BACKORDERED):
        pass  # nothing reserved (a backordered order is just waiting for stock)
    elif order.status == OrderStatus.ALLOCATED:
        skus = _locked_skus_for(order)
        for sku_id, qty in _quantities_by_sku(order).items():
            move_stock(
                skus[sku_id],
                available_delta=qty,
                reserved_delta=-qty,
                reason=StockReason.CANCELLATION,
                actor=actor,
                order=order,
                note="Released by cancellation",
            )
    else:
        raise OrderError(f"Cannot cancel an order in status {order.status}.")

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = timezone.now()
    order.save(update_fields=["status", "cancelled_at"])
    return order


@transaction.atomic
def fulfill_order(*, order, actor):
    """Fulfill an ALLOCATED order: remove its reserved units from stock and mark FULFILLED.

    Double fulfillment is rejected because only ALLOCATED orders are eligible.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)

    if order.status != OrderStatus.ALLOCATED:
        raise OrderError("Only ALLOCATED orders can be fulfilled.")

    skus = _locked_skus_for(order)
    for sku_id, qty in _quantities_by_sku(order).items():
        move_stock(
            skus[sku_id],
            reserved_delta=-qty,
            reason=StockReason.FULFILLMENT,
            actor=actor,
            order=order,
            note="Removed by fulfillment",
        )

    order.status = OrderStatus.FULFILLED
    order.fulfilled_at = timezone.now()
    order.save(update_fields=["status", "fulfilled_at"])
    return order
