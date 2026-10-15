from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError, Q
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from ldap3.core.exceptions import LDAPException
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.permissions import AdminWriteAuthenticatedRead, IsAdminRole

from . import delegation, directory, password_reset, preferences, signatures
from .models import ApprovalLevel, Department, Role, User
from .serializers import (
    ApprovalLevelSerializer, ChangePasswordSerializer, DepartmentSerializer, LoginSerializer,
    MeSerializer, RoleSerializer, UserBriefSerializer, UserSerializer,
)


REMEMBER_SECONDS = 60 * 60 * 24 * 14


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Hands the SPA a CSRF token before its first unsafe request."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = authenticate(request, username=email, password=serializer.validated_data["password"])
        if user is None:
            audit.log(None, "LOGIN_FAILED", f"Failed sign-in attempt for {email}")
            # Same message whether the account exists, is inactive, or the password is wrong.
            return Response({"detail": "Incorrect username or password.", "errors": {}},
                            status=status.HTTP_400_BAD_REQUEST)
        login(request, user)  # rotates the session key
        # "Remember me" keeps the sign-in for two weeks; otherwise it ends with the browser.
        request.session.set_expiry(REMEMBER_SECONDS if serializer.validated_data["remember"] else 0)
        source = "Active Directory" if user.backend.endswith("ActiveDirectoryBackend") else "local account"
        audit.log(user, "LOGIN", f"{user.display_name} signed in ({source})")
        return Response(MeSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetRequestView(APIView):
    """Ask for a reset link. Always answers the same way, whether or not the address has an account."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password_reset"

    def post(self, request):
        email = str(request.data.get("email", ""))[:254]
        if email.strip():
            password_reset.request_reset(email)
        return Response({"detail": "If that address has an account, a message with instructions is on its way."})


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password_reset_confirm"

    def post(self, request):
        data = request.data
        password_reset.confirm_reset(str(data.get("uid", "")), str(data.get("token", "")), str(data.get("new_password", "")))
        return Response({"detail": "Your password has been changed. You can sign in with it now."})


class LogoutView(APIView):
    def post(self, request):
        audit.log(request.user, "LOGOUT", f"{request.user.display_name} signed out")
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        serializer = MeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if isinstance(request.data.get("preferences"), dict):
            preferences.update(request.user, request.data["preferences"])
        return Response(MeSerializer(request.user).data)


class SignatureView(APIView):
    """The signed-in person's own e-signature: view it, replace it, or remove it.

    Nobody can fetch another person's signature here; signatures only leave the
    system printed on the forms they signed.
    """

    parser_classes = [MultiPartParser]

    def get(self, request):
        if not request.user.signature:
            raise Http404
        response = FileResponse(request.user.signature.open("rb"), content_type="image/png")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def post(self, request):
        user = request.user
        image = signatures.normalise(request.FILES.get("file"))
        if user.signature:
            user.signature.delete(save=False)
        user.signature.save(image.name, image, save=True)
        audit.log(user, "SIGNATURE_UPDATED", f"{user.display_name} updated their e-signature")
        return Response(MeSerializer(user).data)

    def delete(self, request):
        user = request.user
        if user.signature:
            user.signature.delete(save=True)
            audit.log(user, "SIGNATURE_REMOVED", f"{user.display_name} removed their e-signature")
        return Response(MeSerializer(user).data)


class DelegationView(APIView):
    """Out-of-office cover: who approves in my place, until when, and whom I am covering for."""

    def _state(self, user):
        cover = delegation.active_delegate(user)
        return {
            "delegate": UserBriefSerializer(cover).data if cover else None,
            "until": user.delegate_until if cover else None,
            "covering_for": [person.display_name for person in delegation.active_delegators(user)],
        }

    def get(self, request):
        return Response(self._state(request.user))

    def put(self, request):
        user, delegate_id, until = request.user, request.data.get("delegate"), request.data.get("until") or None
        username = str(request.data.get("directory_username") or "").strip()
        if not delegate_id and username:
            # A colleague chosen from Active Directory who has no portal account yet: create it now.
            try:
                entry = directory.find(username) if directory.is_configured() else None
            except LDAPException:
                raise ValidationError({"delegate": ["The company directory cannot be reached right now. Try again later."]}) from None
            if entry is None or not entry.email:
                raise ValidationError({"delegate": ["That person was not found in the company directory."]})
            delegate_id = directory.sync_user(entry).pk
        if not delegate_id:
            user.delegate, user.delegate_until = None, None
            user.save(update_fields=["delegate", "delegate_until", "updated_at"])
            audit.log(user, "DELEGATION_ENDED", f"{user.display_name} switched off their out-of-office cover")
            return Response(self._state(user))
        try:
            cover = User.objects.filter(is_active=True).exclude(pk=user.pk).get(pk=delegate_id)
            until = parse_date(until) if until else None
        except (User.DoesNotExist, ValueError, DjangoValidationError):
            raise ValidationError({"delegate": ["Choose an active colleague other than yourself."]}) from None
        if request.data.get("until") and until is None:
            raise ValidationError({"until": ["Enter a valid date."]})
        if until and until < timezone.localdate():
            raise ValidationError({"until": ["The end date cannot be in the past."]})
        if cover.delegate_id == user.pk and delegation.active_delegate(cover):
            raise ValidationError({"delegate": [f"{cover.display_name} has already named you as their cover."]})
        user.delegate, user.delegate_until = cover, until
        user.save(update_fields=["delegate", "delegate_until", "updated_at"])
        audit.log(user, "DELEGATION_SET",
                  f"{user.display_name} named {cover.display_name} to approve in their place"
                  + (f" until {until:%B %d, %Y}" if until else ""))
        return Response(self._state(user))


class ColleagueSearchView(APIView):
    """Find an active colleague by name or email, to name as out-of-office cover."""

    def get(self, request):
        term = request.query_params.get("search", "").strip()
        if len(term) < 2:
            return Response([])
        people = (
            User.objects.filter(is_active=True).exclude(pk=request.user.pk).select_related("department")
            .filter(Q(first_name__icontains=term) | Q(last_name__icontains=term) | Q(email__icontains=term))[:15]
        )
        results = UserBriefSerializer(people, many=True).data
        # With ?directory=1, also offer people in Active Directory who have not signed in yet.
        if request.query_params.get("directory") == "1" and directory.is_configured() and len(results) < 15:
            try:
                entries = directory.search(term)
            except LDAPException:
                entries = []  # directory unreachable: portal accounts only
            known = set(User.objects.filter(
                Q(directory_username__in=[e.username for e in entries]) | Q(email__in=[e.email for e in entries])
            ).values_list("directory_username", "email"))
            taken = {value for pair in known for value in pair if value} | {request.user.email}
            results = list(results) + [
                {"id": None, "directory_username": e.username, "name": f"{e.first_name} {e.last_name}".strip() or e.username,
                 "email": e.email, "position": e.position, "department_name": e.department}
                for e in entries if e.username not in taken and e.email not in taken
            ]
        return Response(results)


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)  # keep this session, drop the others
        audit.log(request.user, "PASSWORD_CHANGED", f"{request.user.display_name} changed their password")
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProtectedDestroyMixin:
    """Turn 'still referenced' database errors into a readable 400."""

    def perform_destroy(self, instance):
        if getattr(instance, "is_system", False):
            raise ValidationError("System records cannot be deleted.")
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError("This record is in use and cannot be deleted. Deactivate it instead.")


class AuditedAdminMixin:
    """Record administrator changes to configuration in the audit trail."""

    audit_label = "record"

    def _audit(self, verb, instance):
        audit.log(self.request.user, f"ADMIN_{verb}",
                  f"{self.request.user.display_name} {verb.lower()} {self.audit_label} “{instance}”")

    def perform_create(self, serializer):
        self._audit("CREATED", serializer.save())

    def perform_update(self, serializer):
        self._audit("UPDATED", serializer.save())

    def perform_destroy(self, instance):
        label = str(instance)
        super().perform_destroy(instance)
        audit.log(self.request.user, "ADMIN_DELETED",
                  f"{self.request.user.display_name} deleted {self.audit_label} “{label}”")


class UserViewSet(AuditedAdminMixin, viewsets.ModelViewSet):
    queryset = User.objects.select_related("department", "approver_level").prefetch_related("roles")
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "post", "patch", "head", "options"]  # users are deactivated, never deleted
    search_fields = ["first_name", "last_name", "email", "employee_id"]
    filterset_fields = ["department", "is_active", "roles__code"]
    ordering_fields = ["first_name", "last_name", "email"]
    audit_label = "user"

    def perform_update(self, serializer):
        user = serializer.instance
        if user.pk == self.request.user.pk:
            data = serializer.validated_data
            losing_admin = "roles" in data and Role.ADMIN not in {r.code for r in data["roles"]}
            if losing_admin or data.get("is_active") is False:
                raise ValidationError("You cannot remove your own administrator access or deactivate yourself.")
        super().perform_update(serializer)


class DepartmentViewSet(AuditedAdminMixin, ProtectedDestroyMixin, viewsets.ModelViewSet):
    queryset = Department.objects.select_related("head")
    serializer_class = DepartmentSerializer
    permission_classes = [AdminWriteAuthenticatedRead]
    pagination_class = None
    search_fields = ["name", "code"]
    audit_label = "department"

    def perform_create(self, serializer):
        self._audit("CREATED", serializer.save(created_by=self.request.user, updated_by=self.request.user))

    def perform_update(self, serializer):
        self._audit("UPDATED", serializer.save(updated_by=self.request.user))


class RoleViewSet(AuditedAdminMixin, ProtectedDestroyMixin, viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [AdminWriteAuthenticatedRead]
    pagination_class = None
    audit_label = "role"


class ApprovalLevelViewSet(AuditedAdminMixin, ProtectedDestroyMixin, viewsets.ModelViewSet):
    queryset = ApprovalLevel.objects.all()
    serializer_class = ApprovalLevelSerializer
    permission_classes = [AdminWriteAuthenticatedRead]
    pagination_class = None
    audit_label = "approval level"
