from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsCustomer, IsOperatorOrAdmin

from .models import Order, OrderStatus
from .serializers import OrderCreateSerializer, OrderReadSerializer
from .services import OrderError, cancel_order, fulfill_order


class OrderViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Orders.

    - create: Customer only (the order_date is server-set, never client-supplied)
    - list/retrieve: a Customer sees only their own orders; Operator/Admin see all
    - cancel: Customer may cancel own PENDING order; Operator/Admin may cancel an ALLOCATED
      order (which releases its reserved stock)
    - fulfill: Operator/Admin only; ALLOCATED -> FULFILLED
    """

    # Class-level queryset lets drf-spectacular type the {id} path param; get_queryset() below
    # is what actually runs (with per-role scoping).
    queryset = Order.objects.all()

    def get_serializer_class(self):
        return OrderCreateSerializer if self.action == "create" else OrderReadSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsCustomer()]
        if self.action == "fulfill":
            return [IsOperatorOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = Order.objects.prefetch_related("lines__sku").select_related("customer")
        user = self.request.user
        if user.is_authenticated and (user.is_warehouse_operator or user.is_admin_role):
            return qs
        return qs.filter(customer=user)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()  # queryset scoping: customers can't reach others' orders (404)

        # A customer may only cancel their own PENDING order; releasing an ALLOCATED order's
        # reserved stock is an Operator/Admin action.
        is_privileged = request.user.is_warehouse_operator or request.user.is_admin_role
        if order.status == OrderStatus.ALLOCATED and not is_privileged:
            return Response(
                {"detail": "Only an operator or admin can cancel an allocated order."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            order = cancel_order(order=order, actor=request.user)
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(OrderReadSerializer(order).data)

    @extend_schema(request=None, responses=OrderReadSerializer)
    @action(detail=True, methods=["post"])
    def fulfill(self, request, pk=None):
        order = self.get_object()
        try:
            order = fulfill_order(order=order, actor=request.user)
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(OrderReadSerializer(order).data)
