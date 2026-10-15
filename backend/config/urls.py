from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Procurement & Payment Portal administration"
admin.site.site_title = "Portal admin"

urlpatterns = [
    # Reachable only where Django itself is reachable; the web server proxies /api only.
    path("django-admin/", admin.site.urls),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.workflows.urls")),
    path("api/", include("apps.requests.urls")),
    path("api/", include("apps.approvals.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.automation.urls")),
    path("api/", include("apps.audit.urls")),
]