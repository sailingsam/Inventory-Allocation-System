"""Celery tasks (bonus): run allocation periodically.

Schedule via Celery beat, e.g. every N minutes, by adding a PeriodicTask through
django-celery-beat (DatabaseScheduler) pointing at `run_allocation_task`.
"""

from celery import shared_task

from .services import perform_allocation_run


@shared_task(name="allocation.run_allocation_task")
def run_allocation_task():
    """Triggered by Celery beat. Runs FCFS allocation with no human actor."""
    run = perform_allocation_run(actor=None)
    return {
        "run_id": run.id,
        "processed": run.orders_processed,
        "allocated": run.orders_allocated,
        "backordered": run.orders_backordered,
    }
