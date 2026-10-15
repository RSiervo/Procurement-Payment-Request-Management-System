from django.urls import path

from . import views

urlpatterns = [
    path("branding/", views.BrandingView.as_view()),
    path("lookups/", views.LookupsView.as_view()),
    path("system-config/", views.SystemConfigView.as_view()),
    path("system-config/logo/", views.LogoView.as_view()),
    path("email-settings/", views.EmailSettingsView.as_view()),
]
