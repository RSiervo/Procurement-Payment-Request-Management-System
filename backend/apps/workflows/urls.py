from rest_framework.routers import SimpleRouter

from .views import WorkflowViewSet

router = SimpleRouter()
router.register("workflows", WorkflowViewSet, basename="workflow")

urlpatterns = router.urls
