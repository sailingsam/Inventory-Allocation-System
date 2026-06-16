"""Audit record for each allocation run (bonus: audit log + summary endpoint).

The FCFS engine itself lives in `services.py`. This model just captures what each run did so
operators can review history and we have an audit trail.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class AllocationRun(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    backorder_on_shortage = models.BooleanField(default=True)

    orders_processed = models.PositiveIntegerField(default=0)
    orders_allocated = models.PositiveIntegerField(default=0)
    orders_backordered = models.PositiveIntegerField(default=0)

    # Per-order outcome detail, e.g. [{"order_id": 1, "outcome": "ALLOCATED"}, ...]
    detail = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return (
            f"Run #{self.pk}: {self.orders_allocated} allocated / "
            f"{self.orders_backordered} backordered of {self.orders_processed}"
        )
