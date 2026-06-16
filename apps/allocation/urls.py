from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AllocationViewSet

router = DefaultRouter()
# Audit log: GET /api/allocation/runs/ and /api/allocation/runs/{id}/
router.register("allocation/runs", AllocationViewSet, basename="allocation-run")

urlpatterns = [
    # The allocation trigger: POST /api/allocation/run/
    path("allocation/run/", AllocationViewSet.as_view({"post": "run"}), name="allocation-run-trigger"),
    *router.urls,
]
