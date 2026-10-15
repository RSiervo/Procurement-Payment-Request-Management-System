from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("users", views.UserViewSet, basename="user")
router.register("departments", views.DepartmentViewSet, basename="department")
router.register("roles", views.RoleViewSet, basename="role")
router.register("approval-levels", views.ApprovalLevelViewSet, basename="approval-level")

urlpatterns = [
    path("auth/csrf/", views.CsrfView.as_view()),
    path("auth/login/", views.LoginView.as_view()),
    path("auth/logout/", views.LogoutView.as_view()),
    path("auth/password-reset/", views.PasswordResetRequestView.as_view()),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
    path("me/", views.MeView.as_view()),
    path("me/signature/", views.SignatureView.as_view()),
    path("me/delegation/", views.DelegationView.as_view()),
    path("colleagues/", views.ColleagueSearchView.as_view()),
    path("me/change-password/", views.ChangePasswordView.as_view()),
    *router.urls,
]
