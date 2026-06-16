"""Root URL configuration.

App-specific routes are added under /api/ as each app is built. OpenAPI schema and Swagger UI
expose the machine-readable API contract.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def healthcheck(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="health"),
    # OpenAPI contract
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # App routes
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.inventory.urls")),
    #   path("api/", include("apps.orders.urls")),
    #   path("api/", include("apps.allocation.urls")),
]
