"""Stock mutation service.

All stock changes funnel through here so that (a) they are validated against the
non-negative invariant and (b) every change appends a StockLedger row. Callers that already
hold a row lock use `move_stock`; the convenience `adjust_stock` acquires the lock itself.

This module is infrastructure shared by orders and allocation. It deliberately contains NO
FCFS decision logic (which order, in what order, all-or-nothing) — that lives in the
allocation engine.
"""

from django.db import transaction

from .models import SKU, StockLedger, StockReason


class InsufficientStock(Exception):
    """Raised when a stock movement would drive available or reserved below zero."""

    def __init__(self, sku, message="Insufficient stock for this movement"):
        self.sku = sku
        super().__init__(message)


def move_stock(sku, *, available_delta=0, reserved_delta=0, reason, actor=None, note=""):
    """Apply signed deltas to an ALREADY-LOCKED SKU and append a ledger row.

    The caller is responsible for holding the row lock (`select_for_update`) so that concurrent
    callers serialize. Returns the created StockLedger entry.

    (Stage 4 adds an optional `order=` kwarg to link movements to the causing order.)
    """
    new_available = sku.available_quantity + available_delta
    new_reserved = sku.reserved_quantity + reserved_delta
    if new_available < 0 or new_reserved < 0:
        raise InsufficientStock(sku)

    sku.available_quantity = new_available
    sku.reserved_quantity = new_reserved
    sku.save(update_fields=["available_quantity", "reserved_quantity", "updated_at"])

    return StockLedger.objects.create(
        sku=sku,
        available_change=available_delta,
        reserved_change=reserved_delta,
        available_after=new_available,
        reserved_after=new_reserved,
        reason=reason,
        actor=actor,
        note=note,
    )


@transaction.atomic
def adjust_stock(*, sku_id, available_delta, reason=StockReason.ADJUSTMENT, actor=None, note=""):
    """Operator/Admin stock adjustment (restock or correction). Locks the SKU row, applies the
    change to available_quantity, and records it in the ledger.
    """
    sku = SKU.objects.select_for_update().get(pk=sku_id)
    move_stock(sku, available_delta=available_delta, reason=reason, actor=actor, note=note)
    return sku
