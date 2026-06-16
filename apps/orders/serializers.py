from rest_framework import serializers

from apps.inventory.models import SKU

from .models import Order, OrderLine
from .services import create_order


class OrderLineReadSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source="sku.code", read_only=True)

    class Meta:
        model = OrderLine
        fields = ("id", "sku", "sku_code", "quantity")


class OrderLineWriteSerializer(serializers.Serializer):
    sku = serializers.PrimaryKeyRelatedField(queryset=SKU.objects.all())
    quantity = serializers.IntegerField(min_value=1)


class OrderReadSerializer(serializers.ModelSerializer):
    lines = OrderLineReadSerializer(many=True, read_only=True)
    customer_email = serializers.CharField(source="customer.email", read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "customer",
            "customer_email",
            "order_date",
            "status",
            "created_at",
            "allocated_at",
            "fulfilled_at",
            "cancelled_at",
            "lines",
        )
        read_only_fields = fields


class OrderCreateSerializer(serializers.Serializer):
    """Customer order creation. Note: `order_date` is intentionally NOT accepted here — it is
    server-set (immutable from the API) and may only be backdated via seed/admin.
    """

    lines = OrderLineWriteSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("An order must have at least one line.")
        return value

    def create(self, validated_data):
        customer = self.context["request"].user
        lines = [(item["sku"], item["quantity"]) for item in validated_data["lines"]]
        return create_order(customer=customer, lines=lines)

    def to_representation(self, instance):
        return OrderReadSerializer(instance, context=self.context).data
