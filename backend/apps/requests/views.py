from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.approvals import services as approvals
from apps.approvals import timeline
from apps.approvals.models import ActionType
from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer
from apps.core.models import SystemConfig
from apps.core.permissions import AdminWriteAuthenticatedRead, IsAdminRole
from apps.core.utils import format_quantity
from apps.notifications.models import Notification
from apps.notifications.serializers import RequestNotificationSerializer
from apps.reports.exporters import EXPORTERS
from apps.users.models import Role
from apps.users.views import AuditedAdminMixin, ProtectedDestroyMixin

from . import selectors, services
from .filters import RequestFilter
from .models import Budget, ExpenseCategory, Request, RequestType, Status, Vendor
from .pdf import render_request_pdf
from .purchase_order import render_purchase_order
from .serializers import (
    AttachmentSerializer, AttachmentUploadSerializer, BudgetSerializer, CommentSerializer, DecisionSerializer, VendorSerializer,
    ExpenseCategorySerializer, OpsStatusSerializer, OpsUpdateSerializer, RequestBriefSerializer,
    RequestDetailSerializer, RequestListSerializer, RequestTypeSerializer, RequestWriteSerializer,
    PurchaseOrderSerializer, RoutePreviewSerializer,
)
from .validators import INLINE_TYPES


def _line_label(line):
    return f"{format_quantity(line.quantity)} × {line.description}" if line.quantity else line.description


class RequestViewSet(viewsets.ModelViewSet):
    """Requests of every type. Visibility is enforced by the queryset, rules by the services."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filterset_class = RequestFilter
    search_fields = ["number", "requester__first_name", "requester__last_name", "department__name",
                     "payable_to", "purpose", "lines__description"]
    ordering_fields = ["created_at", "updated_at", "submitted_at", "total_amount", "number", "date_needed"]
    ordering = ["-updated_at"]

    def get_queryset(self):
        qs = selectors.base_queryset(self.request.user)
        if self.action == "list" and self.request.query_params.get("search"):
            qs = qs.distinct()  # searching line descriptions can duplicate rows
        return qs

    def get_serializer_class(self):
        return RequestListSerializer if self.action == "list" else RequestDetailSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "ops_sla_days": SystemConfig.load().ops_sla_days}

    def _detail(self, req, status_code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=req.pk)
        return Response(RequestDetailSerializer(fresh, context=self.get_serializer_context()).data, status=status_code)

    # --- drafting ---
    def create(self, request, *args, **kwargs):
        serializer = RequestWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = services.save_draft(request.user, serializer.validated_data)
        return self._detail(req, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        req = self.get_object()
        serializer = RequestWriteSerializer(req, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return self._detail(services.save_draft(request.user, serializer.validated_data, req))

    def destroy(self, request, *args, **kwargs):
        services.delete_draft(request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="route-preview")
    def route_preview(self, request):
        """Which approval route a request with these details would take."""
        serializer = RoutePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        department = data.get("department") or request.user.department
        return Response({"route": services.describe_route(data["request_type"], department, data["amount"], request.user)})

    @action(detail=False, methods=["get"])
    def export(self, request):
        """The request list as a spreadsheet, with whatever search and filters are applied to it."""
        export_format = request.query_params.get("file_format", "xlsx")
        if export_format not in ("csv", "xlsx"):
            raise ValidationError("Unsupported export format. Use csv or xlsx.")
        rows = [
            [r.display_number, r.request_type.name, r.get_status_display(), r.get_priority_display(),
             r.requester.display_name, r.department.name, r.payable_to, r.total_amount, r.current_handler,
             timezone.localtime(r.submitted_at).date() if r.submitted_at else "",
             r.date_needed or "", timezone.localtime(r.completed_at).date() if r.completed_at else "",
             r.po_number, r.invoice_number]
            for r in self.filter_queryset(self.get_queryset())[:5000]
        ]
        headers = ["Request #", "Type", "Status", "Priority", "Requester", "Department", "Payable to", "Amount",
                   "Currently with", "Submitted", "Date needed", "Completed", "PO #", "Invoice #"]
        audit.log(request.user, "REQUESTS_EXPORTED",
                  f"{request.user.display_name} exported the request list as {export_format.upper()}",
                  metadata={"rows": len(rows)})
        return EXPORTERS[export_format]("Requests", headers, rows, f"requests-{timezone.localdate():%Y%m%d}")

    @action(detail=False, methods=["get"])
    def linkable(self, request):
        """Approved purchase requisitions a payment can be linked to; with ?kind=advance,
        the person's own approved cash advances that still need a liquidation."""
        if request.query_params.get("kind") == "advance":
            owner = request.query_params.get("requester") or request.user.pk
            liquidated = Request.objects.filter(request_type__code=RequestType.LIQ, source_request__isnull=False).exclude(
                status__in=[Status.REJECTED, Status.CANCELLED]).values("source_request_id")
            try:
                qs = self.get_queryset().filter(
                    request_type__code=RequestType.CA, requester_id=owner, status__in=services.LINKABLE_STATUSES
                ).exclude(pk__in=liquidated).prefetch_related("lines")
                qs.exists()
            except (DjangoValidationError, ValueError):
                return Response([])
        else:
            qs = self.get_queryset().filter(
                request_type__code=RequestType.PR, status__in=services.LINKABLE_STATUSES
            ).prefetch_related("lines")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(number__icontains=search)
        data = []
        for pr in qs.order_by("-approved_at")[:25]:
            row = RequestBriefSerializer(pr).data
            lines = list(pr.lines.all())
            row.update(
                department=pr.department_id, department_name=pr.department.name,
                requester_name=pr.requester.display_name,
                summary=", ".join(_line_label(line) for line in lines[:3]) + ("…" if len(lines) > 3 else ""),
                lines=[{"description": _line_label(line), "remarks": line.remarks, "amount": line.amount} for line in lines],
            )
            data.append(row)
        return Response(data)

    # --- workflow actions ---
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._detail(services.submit(request.user, self.get_object()))

    def _decide(self, request, action_type):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = services.lock(self.get_object())
        approvals.act(req, request.user, action_type, serializer.validated_data["comments"])
        return self._detail(req)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, ActionType.APPROVE)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, ActionType.REJECT)

    @action(detail=True, methods=["post"], url_path="return")
    def return_for_revision(self, request, pk=None):
        return self._decide(request, ActionType.RETURN)

    @action(detail=True, methods=["post"])
    def clarify(self, request, pk=None):
        return self._decide(request, ActionType.CLARIFY)

    @action(detail=True, methods=["post"], url_path="hand-over")
    def hand_over(self, request, pk=None):
        return self._detail(services.hand_over(request.user, self.get_object()))

    @action(detail=True, methods=["get", "post"], url_path="purchase-order")
    def purchase_order(self, request, pk=None):
        """POST (OPS): issue or update the purchase order. GET: the printable purchase order."""
        req = self.get_object()
        if request.method == "POST":
            serializer = PurchaseOrderSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            return self._detail(services.issue_purchase_order(request.user, req, data["supplier"], data["terms"]))
        if not req.po_date:
            raise ValidationError("No purchase order has been issued for this requisition yet.")
        response = HttpResponse(render_purchase_order(req), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{req.po_number}.pdf"'
        return response

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._detail(services.cancel(request.user, self.get_object(), serializer.validated_data["comments"]))

    # --- OPS processing ---
    @action(detail=True, methods=["patch"], url_path="ops")
    def ops_update(self, request, pk=None):
        serializer = OpsUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return self._detail(services.ops_update(request.user, self.get_object(), serializer.validated_data))

    @action(detail=True, methods=["post"], url_path="ops/status")
    def ops_status(self, request, pk=None):
        serializer = OpsStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self._detail(services.ops_transition(request.user, self.get_object(), data["status"], data["remarks"]))

    # --- history ---
    @action(detail=True, methods=["get"], url_path="timeline")
    def timeline(self, request, pk=None):
        return Response(timeline.build(self.get_object()))

    @action(detail=True, methods=["get"], url_path="audit-log")
    def audit_log(self, request, pk=None):
        logs = AuditLog.objects.filter(request=self.get_object()).select_related("actor")
        show_client = request.user.has_role(Role.ADMIN)
        return Response(AuditLogSerializer(logs, many=True, context={"show_client": show_client}).data)

    @action(detail=True, methods=["get"])
    def notifications(self, request, pk=None):
        """Notifications sent about this request. Non-privileged users see only their own."""
        req = self.get_object()
        notes = Notification.objects.filter(request=req).select_related("recipient")
        user = request.user
        if not (services.is_owner(user, req) or user.has_role(Role.ADMIN, Role.OPS)):
            notes = notes.filter(recipient=user)
        return Response(RequestNotificationSerializer(notes[:100], many=True).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        req = self.get_object()
        if request.method == "POST":
            comment = services.add_comment(request.user, req, request.data.get("body", ""))
            return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)
        return Response(CommentSerializer(req.comments.select_related("author"), many=True).data)

    # --- documents ---
    @action(detail=True, methods=["get", "post"])
    def attachments(self, request, pk=None):
        req = self.get_object()
        if request.method == "POST":
            serializer = AttachmentUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            attachment = services.add_attachment(request.user, req, data["file"], data["kind"])
            return Response(AttachmentSerializer(attachment, context=self.get_serializer_context()).data,
                            status=status.HTTP_201_CREATED)
        attachments = req.attachments.select_related("uploaded_by", "request")
        return Response(AttachmentSerializer(attachments, many=True, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get", "delete"], url_path=r"attachments/(?P<attachment_id>[0-9a-f-]{36})")
    def attachment(self, request, pk=None, attachment_id=None):
        """Download (GET) or remove (DELETE) one document. Access follows the request's visibility."""
        attachment = get_object_or_404(self.get_object().attachments, pk=attachment_id)
        if request.method == "DELETE":
            services.delete_attachment(request.user, attachment)
            return Response(status=status.HTTP_204_NO_CONTENT)
        inline = attachment.content_type in INLINE_TYPES and request.query_params.get("inline") == "1"
        response = FileResponse(attachment.file.open("rb"), content_type=attachment.content_type,
                                as_attachment=not inline, filename=attachment.original_name)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        req = self.get_object()
        response = HttpResponse(render_request_pdf(req), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{req.display_number}.pdf"'
        return response


class VerifyView(APIView):
    """What a printed form's QR code shows: enough to confirm the paper is genuine, and nothing more.

    Open to anyone holding the form, without signing in. It gives the number, status,
    amount and who signed when; never the items, attachments, comments or purpose.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "verify"

    def get(self, request, pk):
        req = get_object_or_404(
            Request.objects.exclude(status=Status.DRAFT).select_related("request_type", "requester", "department"), pk=pk
        )
        config = SystemConfig.load()
        steps = [
            {"label": node["label"], "state": node["state"], "detail": node["detail"],
             "actor": node["actor"] if node["state"] != "upcoming" else "", "at": node["at"]}
            for node in timeline.build(req)["current"]
        ]
        return Response({
            "company_name": config.company_name, "currency_symbol": config.currency_symbol,
            "number": req.number, "type_name": req.request_type.name,
            "status": req.status, "status_display": req.get_status_display(),
            "total_amount": req.total_amount, "department_name": req.department.name,
            "requester_name": req.requester.display_name,
            "submitted_at": req.submitted_at, "completed_at": req.completed_at, "steps": steps,
        })


class RequestTypeViewSet(AuditedAdminMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Request types are defined in code (each needs a form layout); admins tune their settings."""

    queryset = RequestType.objects.all()
    serializer_class = RequestTypeSerializer
    permission_classes = [AdminWriteAuthenticatedRead]
    pagination_class = None
    http_method_names = ["get", "patch", "head", "options"]
    audit_label = "request type"


class VendorViewSet(AuditedAdminMixin, ProtectedDestroyMixin, viewsets.ModelViewSet):
    """The vendor list, kept by administrators. Everyone else only sees the names (lookups)."""

    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsAdminRole]
    pagination_class = None
    search_fields = ["name", "tin"]
    audit_label = "vendor"


class BudgetViewSet(AuditedAdminMixin, viewsets.ModelViewSet):
    """Department budgets per year. Administrators set them; Finance can read them."""

    queryset = Budget.objects.select_related("department")
    serializer_class = BudgetSerializer
    permission_classes = [AdminWriteAuthenticatedRead]
    pagination_class = None
    audit_label = "budget"

    def get_queryset(self):
        if not self.request.user.has_role(Role.ADMIN, Role.FINANCE):
            return self.queryset.none()
        return self.queryset


class ExpenseCategoryViewSet(AuditedAdminMixin, ProtectedDestroyMixin, viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer
    permission_classes = [AdminWriteAuthenticatedRead]
    pagination_class = None
    audit_label = "expense category"

    def get_queryset(self):
        if not self.request.user.has_role(Role.ADMIN):
            return self.queryset.filter(is_active=True)
        return self.queryset

