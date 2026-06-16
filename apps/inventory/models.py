"""Inventory: SKUs and an append-only stock ledger.

Stock is tracked as two non-negative counters per SKU:
  - available_quantity: on hand and free to be reserved
  - reserved_quantity:  committed to ALLOCATED (not-yet-fulfilled) orders

Allocation moves units available -> reserved; fulfillment removes them from reserved;
cancellation of an allocated order moves reserved -> available.
"""

from django.conf import settings
from django.db import models


class SKU(models.Model):
    code = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    available_quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(available_quantity__gte=0), name="sku_available_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(reserved_quantity__gte=0), name="sku_reserved_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.code} (avail={self.available_quantity}, reserved={self.reserved_quantity})"


class StockReason(models.TextChoices):
    RESTOCK = "RESTOCK", "Restock"
    ADJUSTMENT = "ADJUSTMENT", "Manual adjustment"
    ALLOCATION = "ALLOCATION", "Reserved by allocation"
    CANCELLATION = "CANCELLATION", "Released by cancellation"
    FULFILLMENT = "FULFILLMENT", "Removed by fulfillment"


class StockLedger(models.Model):
    """Append-only audit trail: one row per stock movement (never updated/deleted)."""

    sku = models.ForeignKey(SKU, on_delete=models.PROTECT, related_name="ledger_entries")
    available_change = models.IntegerField(help_text="Signed delta applied to available_quantity")
    reserved_change = models.IntegerField(help_text="Signed delta applied to reserved_quantity")
    available_after = models.PositiveIntegerField()
    reserved_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=32, choices=StockReason.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    # NOTE: an optional FK to orders.Order is added in Stage 4 so allocation/fulfil/cancel
    # movements link back to the order that caused them.
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.sku.code} {self.reason} a{self.available_change:+d}/r{self.reserved_change:+d}"
