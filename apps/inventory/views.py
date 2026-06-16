from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsOperatorOrAdmin

from .models import SKU
from .serializers import SKUSerializer, StockAdjustSerializer
from .services import InsufficientStock, adjust_stock


class SKUViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """SKU catalogue.

    - list/retrieve: any authenticated user
    - create + stock adjust: Operator/Admin only
    """

    queryset = SKU.objects.all()
    serializer_class = SKUSerializer

    def get_permissions(self):
        if self.action in ("create", "adjust_stock"):
            return [IsOperatorOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(request=StockAdjustSerializer, responses=SKUSerializer)
    @action(detail=True, methods=["patch"], url_path="stock")
    def adjust_stock(self, request, pk=None):
        """Operator/Admin: adjust available stock (restock/correction). Writes to the ledger."""
        serializer = StockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sku = adjust_stock(
                sku_id=pk,
                available_delta=serializer.validated_data["available_delta"],
                reason=serializer.validated_data["reason"],
                actor=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except SKU.DoesNotExist:
            return Response({"detail": "SKU not found."}, status=status.HTTP_404_NOT_FOUND)
        except InsufficientStock:
            return Response(
                {"detail": "Adjustment would make available stock negative."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(SKUSerializer(sku).data, status=status.HTTP_200_OK)
