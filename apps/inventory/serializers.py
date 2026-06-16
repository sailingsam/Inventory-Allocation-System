from rest_framework import serializers

from .models import SKU, StockLedger, StockReason


class SKUSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKU
        fields = (
            "id",
            "code",
            "name",
            "available_quantity",
            "reserved_quantity",
            "created_at",
            "updated_at",
        )
        # Quantities are mutated only through the ledgered stock service, never edited directly.
        read_only_fields = ("id", "reserved_quantity", "created_at", "updated_at")


class StockAdjustSerializer(serializers.Serializer):
    """Body for PATCH /api/skus/{id}/stock/ — a signed delta plus a reason."""

    available_delta = serializers.IntegerField(
        help_text="Signed change to available stock (e.g. +50 restock, -5 correction)."
    )
    reason = serializers.ChoiceField(
        choices=[StockReason.RESTOCK, StockReason.ADJUSTMENT],
        default=StockReason.RESTOCK,
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_available_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("available_delta must be non-zero.")
        return value


class StockLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLedger
        fields = (
            "id",
            "sku",
            "available_change",
            "reserved_change",
            "available_after",
            "reserved_after",
            "reason",
            "actor",
            "note",
            "created_at",
        )
        read_only_fields = fields
