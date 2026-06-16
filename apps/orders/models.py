"""Orders and their line items.

`order_date` drives FCFS allocation priority. It defaults to now() but may be backdated via
seed/admin (never through the customer-facing API), so historical demos can be reproduced.
`created_at` is the tiebreaker when two orders share an order_date.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class OrderStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ALLOCATED = "ALLOCATED", "Allocated"
    FULFILLED = "FULFILLED", "Fulfilled"
    CANCELLED = "CANCELLED", "Cancelled"
    BACKORDERED = "BACKORDERED", "Backordered"


class Order(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    # Immutable priority key for FCFS. Default now(); backdated only via seed/admin.
    order_date = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(
        max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    allocated_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # Natural FCFS ordering: by order_date, then created_at as the tiebreaker.
        ordering = ["order_date", "created_at", "id"]
        indexes = [models.Index(fields=["status", "order_date", "created_at"])]

    def __str__(self):
        return f"Order #{self.pk} [{self.status}] {self.order_date:%Y-%m-%d}"


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    sku = models.ForeignKey("inventory.SKU", on_delete=models.PROTECT, related_name="order_lines")
    quantity = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="orderline_qty_positive"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.sku.code} (order #{self.order_id})"
