from rest_framework import serializers

from .models import AllocationRun


class AllocationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllocationRun
        fields = (
            "id",
            "actor",
            "started_at",
            "finished_at",
            "backorder_on_shortage",
            "orders_processed",
            "orders_allocated",
            "orders_backordered",
            "detail",
        )
        read_only_fields = fields
