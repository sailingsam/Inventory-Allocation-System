from rest_framework.routers import DefaultRouter

from .views import SKUViewSet

router = DefaultRouter()
router.register("skus", SKUViewSet, basename="sku")

urlpatterns = router.urls
