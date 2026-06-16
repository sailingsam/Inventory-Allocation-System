from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import IsOperatorOrAdmin

from .models import AllocationRun
from .serializers import AllocationRunSerializer
from .services import perform_allocation_run


class AllocationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Allocation runs (Operator/Admin only).

    - POST /api/allocation/run/       -> execute an FCFS allocation run, returns its summary
    - GET  /api/allocation/runs/      -> audit log of past runs (bonus)
    - GET  /api/allocation/runs/{id}/ -> a single run's detail
    """

    queryset = AllocationRun.objects.all()
    serializer_class = AllocationRunSerializer
    permission_classes = [IsOperatorOrAdmin]

    @extend_schema(request=None, responses=AllocationRunSerializer)
    def run(self, request):
        """Execute an FCFS allocation run (mapped to POST /api/allocation/run/)."""
        run = perform_allocation_run(actor=request.user)
        return Response(AllocationRunSerializer(run).data)
