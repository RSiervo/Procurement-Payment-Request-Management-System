from django.urls import path

from . import views

urlpatterns = [
    path("automations/", views.AutomationListView.as_view()),
    path("automations/<slug:key>/", views.AutomationView.as_view()),
    path("automations/<slug:key>/run/", views.AutomationRunView.as_view()),
]