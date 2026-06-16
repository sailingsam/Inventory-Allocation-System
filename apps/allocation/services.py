"""FCFS allocation engine + audit wrapper.

────────────────────────────────────────────────────────────────────────────────────────────
  STAGE 5 — CANDIDATE-AUTHORED.  `run_allocation()` below is intentionally left UNIMPLEMENTED.
  The FCFS decision logic is the heart of this assignment and (per the brief) must be written
  by the candidate, not generated. Everything around it — the result contract, the audit
  wrapper that persists an AllocationRun, the API view, the Celery task — is already in place,
  so implementing the engine is purely the ~40-line FCFS loop.
────────────────────────────────────────────────────────────────────────────────────────────

CONTRACT for run_allocation():
    Inputs:
        actor                  -> the User triggering the run (for ledger attribution), or None
        backorder_on_shortage  -> bool; when True a fully-unfulfillable order becomes BACKORDERED,
                                  when False it stays PENDING for a later run to retry
    Must:
        - process PENDING orders in FCFS priority: order_date ASC, then created_at ASC
        - be concurrency-safe (advisory lock for one-run-at-a-time + select_for_update on rows)
        - all-or-nothing per order (no partial allocation)
        - reserve stock via inventory.services.move_stock (available -> reserved) on success
        - set status/allocated_at; write ledger entries linked to the order
    Returns:
        AllocationResult summarising the run (used by the audit wrapper below).
"""

from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from .models import AllocationRun


@dataclass
class AllocationResult:
    """Summary returned by the engine and persisted into an AllocationRun."""

    processed: int = 0
    allocated_order_ids: list[int] = field(default_factory=list)
    backordered_order_ids: list[int] = field(default_factory=list)
    detail: list[dict] = field(default_factory=list)


def run_allocation(*, actor=None, backorder_on_shortage=None) -> AllocationResult:
    """The FCFS allocation engine. CANDIDATE TO IMPLEMENT (Stage 5).

    See the module docstring for the full contract.
    """
    raise NotImplementedError(
        "Allocation engine not implemented yet — this is the candidate-authored Stage 5 loop."
    )


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
