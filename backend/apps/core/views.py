from django.conf import settings
from django.core.mail import send_mail
from django.http import FileResponse, Http404
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.requests.models import ExpenseCategory, RequestType, Vendor
from apps.requests.serializers import ExpenseCategorySerializer, RequestTypeSerializer
from apps.users.models import Department, Role, User
from apps.users.serializers import UserBriefSerializer

from .models import SystemConfig
from .permissions import AdminWriteAuthenticatedRead, IsAdminRole


class SystemConfigSerializer(serializers.ModelSerializer):
    has_logo = serializers.SerializerMethodField()
    logo = serializers.ImageField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = SystemConfig
        fields = [
            "company_name", "company_address", "logo", "has_logo", "currency_code", "currency_symbol",
            "allow_self_approval", "ops_sla_days", "max_upload_mb", "reminder_after_days", "escalate_after_days",
            "block_over_budget",
        ]

    def get_has_logo(self, obj):
        return bool(obj.logo)

    def validate_max_upload_mb(self, value):
        if not 1 <= value <= 25:
            raise serializers.ValidationError("Choose a limit between 1 and 25 MB.")
        return value


class SystemConfigView(APIView):
    permission_classes = [AdminWriteAuthenticatedRead]

    def get(self, request):
        return Response(SystemConfigSerializer(SystemConfig.load()).data)

    def patch(self, request):
        config = SystemConfig.load()
        serializer = SystemConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        audit.log(request.user, "ADMIN_UPDATED", f"{request.user.display_name} updated system configuration",
                  metadata={"fields": sorted(serializer.validated_data)})
        return Response(serializer.data)


class LogoView(APIView):
    """The company logo. Public, because the sign-in page shows it."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        config = SystemConfig.load()
        if not config.logo:
            raise Http404
        return FileResponse(config.logo.open("rb"))


class BrandingView(APIView):
    """What the sign-in page shows before anyone is signed in. Nothing sensitive."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        config = SystemConfig.load()
        return Response({"company_name": config.company_name, "has_logo": bool(config.logo)})


class LookupsView(APIView):
    """Reference data every screen needs, in one round trip."""

    def get(self, request):
        ops_users = User.objects.filter(roles__code=Role.OPS, is_active=True).select_related("department")
        departments = Department.objects.filter(is_active=True).values("id", "code", "name")
        return Response({
            "request_types": RequestTypeSerializer(RequestType.objects.filter(is_active=True), many=True).data,
            "departments": list(departments),
            "expense_categories": ExpenseCategorySerializer(
                ExpenseCategory.objects.filter(is_active=True), many=True
            ).data,
            "vendors": list(Vendor.objects.filter(is_active=True).values_list("name", flat=True)),
            "ops_users": UserBriefSerializer(ops_users, many=True).data,
            "config": SystemConfigSerializer(SystemConfig.load()).data,
        })


class EmailSettingsView(APIView):
    """Read-only view of the SMTP configuration (set through environment variables)."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response({
            "configured": bool(settings.EMAIL_HOST),
            "backend": "SMTP" if settings.EMAIL_HOST else "Console (emails are printed to the server log)",
            "host": settings.EMAIL_HOST,
            "port": settings.EMAIL_PORT,
            "username": settings.EMAIL_HOST_USER,
            "use_tls": settings.EMAIL_USE_TLS,
            "from_email": settings.DEFAULT_FROM_EMAIL,
            "frontend_url": settings.FRONTEND_URL,
        })

    def post(self, request):
        """Send a test message to the signed-in administrator."""
        try:
            send_mail(
                "Test email — Procurement & Payment Portal",
                "This is a test message. If you received it, outgoing email is working.",
                None,
                [request.user.email],
            )
        except Exception as exc:
            return Response({"detail": f"Sending failed: {exc}", "errors": {}}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detail": f"Test email sent to {request.user.email}."})
