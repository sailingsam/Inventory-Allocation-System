"""FCFS allocation engine + audit wrapper.

`run_allocation()` is the heart of the system: it walks all PENDING orders in First-Come-
First-Serve priority (by `order_date`, then `created_at`) and reserves stock for each order it
can fully satisfy. It is concurrency-safe (advisory lock + row locks) and never partially
allocates an order (all-or-nothing).
"""

from collections import defaultdict
from dataclasses import dataclass, field

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.inventory.models import SKU, StockReason
from apps.inventory.services import move_stock
from apps.orders.models import Order, OrderStatus

from .models import AllocationRun

# A fixed key so every allocation run contends for the SAME Postgres advisory lock — this is
# what guarantees only one run is ever effective at a time.
ADVISORY_LOCK_KEY = 91823744


@dataclass
class AllocationResult:
    """Summary returned by the engine and persisted into an AllocationRun."""

    processed: int = 0
    allocated_order_ids: list[int] = field(default_factory=list)
    backordered_order_ids: list[int] = field(default_factory=list)
    detail: list[dict] = field(default_factory=list)


def run_allocation(*, actor=None, backorder_on_shortage=None) -> AllocationResult:
    """Run one FCFS allocation pass.

    Args:
        actor: the user triggering the run (recorded on ledger entries), or None for a job.
        backorder_on_shortage: when True, an order that cannot be fully satisfied is marked
            BACKORDERED; when False it is left PENDING so a later run can retry it. Defaults to
            the ALLOCATION_BACKORDER_ON_SHORTAGE setting.
    """
    if backorder_on_shortage is None:
        backorder_on_shortage = settings.ALLOCATION_BACKORDER_ON_SHORTAGE

    result = AllocationResult()

    # The whole run is one transaction: either the consistent set of reservations commits, or
    # nothing does.
    with transaction.atomic():
        # (1) Only one allocation run effective at a time. The advisory lock is held until this
        #     transaction ends, so a second concurrent run blocks here until we finish.
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [ADVISORY_LOCK_KEY])

        # (2) The FCFS queue: every order that still needs stock — both PENDING and previously
        #     BACKORDERED — oldest order_date first (created_at breaks ties). Including
        #     BACKORDERED means an order that couldn't be filled earlier is re-checked on every
        #     run (e.g. after a restock) and, thanks to the order_date sort, keeps its original
        #     FCFS priority ahead of newer orders.
        #     We lock these order rows so a concurrent cancel/fulfill on the same order waits
        #     for us (they also lock the order row).
        outstanding_orders = (
            Order.objects.filter(status__in=(OrderStatus.PENDING, OrderStatus.BACKORDERED))
            .order_by("order_date", "created_at", "id")
            .select_for_update()
        )

        for order in outstanding_orders:
            result.processed += 1

            # Total quantity required per SKU (an order can have multiple lines for one SKU).
            required = defaultdict(int)
            for line in order.lines.all():
                required[line.sku_id] += line.quantity

            # (3) Lock the SKU rows this order touches, always in id order to avoid deadlocks.
            skus = {
                sku.id: sku
                for sku in SKU.objects.select_for_update()
                .filter(id__in=required.keys())
                .order_by("id")
            }

            # (4) All-or-nothing: every line must fit in available stock, or we allocate none.
            can_fulfill = all(
                skus[sku_id].available_quantity >= qty for sku_id, qty in required.items()
            )

            if can_fulfill:
                for sku_id, qty in required.items():
                    # Reserve: move units from available -> reserved (and write the ledger).
                    move_stock(
                        skus[sku_id],
                        available_delta=-qty,
                        reserved_delta=qty,
                        reason=StockReason.ALLOCATION,
                        actor=actor,
                        order=order,
                        note="Reserved by allocation run",
                    )
                order.status = OrderStatus.ALLOCATED
                order.allocated_at = timezone.now()
                order.save(update_fields=["status", "allocated_at"])
                result.allocated_order_ids.append(order.id)
                result.detail.append({"order_id": order.id, "outcome": "ALLOCATED"})
            else:
                # Shortage. We do NOT partially allocate, and we do NOT stop the run — later,
                # smaller orders may still fit ("continue past shortages"). The order stays
                # outstanding and is re-checked on the next run, keeping its FCFS priority.
                if backorder_on_shortage:
                    if order.status != OrderStatus.BACKORDERED:
                        order.status = OrderStatus.BACKORDERED
                        order.save(update_fields=["status"])
                    result.backordered_order_ids.append(order.id)
                    result.detail.append({"order_id": order.id, "outcome": "BACKORDERED"})
                else:
                    result.detail.append({"order_id": order.id, "outcome": "LEFT_PENDING"})

    return result


def perform_allocation_run(*, actor=None) -> AllocationRun:
    """Audit wrapper (plumbing): time the run, invoke the engine, persist an AllocationRun.

    The engine owns its own transaction + advisory lock; this wrapper only records the outcome.
    """
    backorder = settings.ALLOCATION_BACKORDER_ON_SHORTAGE
    run = AllocationRun.objects.create(
        actor=actor, started_at=timezone.now(), backorder_on_shortage=backorder
    )
    result = run_allocation(actor=actor, backorder_on_shortage=backorder)
    run.finished_at = timezone.now()
    run.orders_processed = result.processed
    run.orders_allocated = len(result.allocated_order_ids)
    run.orders_backordered = len(result.backordered_order_ids)
    run.detail = result.detail
    run.save()
    return run
