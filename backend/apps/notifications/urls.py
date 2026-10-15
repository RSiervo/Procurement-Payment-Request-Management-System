from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("notifications", views.NotificationViewSet, basename="notification")
router.register("notification-templates", views.NotificationTemplateViewSet, basename="notification-template")

urlpatterns = router.urls
