from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("requests", views.RequestViewSet, basename="request")
router.register("request-types", views.RequestTypeViewSet, basename="request-type")
router.register("expense-categories", views.ExpenseCategoryViewSet, basename="expense-category")
router.register("vendors", views.VendorViewSet, basename="vendor")
router.register("budgets", views.BudgetViewSet, basename="budget")

urlpatterns = [path("verify/<uuid:pk>/", views.VerifyView.as_view()), *router.urls]
