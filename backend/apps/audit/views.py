from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardPagination
from apps.core.permissions import IsAdminRole
from apps.reports.exporters import EXPORTERS

from . import services
from .models import AuditLog


def _filtered(params):
    """The audit trail narrowed by the viewer's search, action and dates."""
    logs = AuditLog.objects.select_related("actor", "request")
    search = params.get("search", "").strip()
    if search:
        logs = logs.filter(
            Q(message__icontains=search) | Q(comments__icontains=search) | Q(request__number__icontains=search)
            | Q(actor__first_name__icontains=search) | Q(actor__last_name__icontains=search)
            | Q(actor__email__icontains=search) | Q(ip_address__icontains=search)
        )
    if params.get("action"):
        logs = logs.filter(action=params["action"])
    for name, lookup in (("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")):
        if params.get(name):
            day = parse_date(params[name])
            if day is None:
                raise ValidationError({name: ["Enter a valid date."]})
            logs = logs.filter(**{lookup: day})
    return logs


def _row(log):
    return {
        "id": log.id, "created_at": log.created_at, "action": log.action, "message": log.message,
        "actor_name": log.actor.display_name if log.actor_id else "System",
        "request_id": log.request_id, "request_number": log.request.number if log.request_id else "",
        "comments": log.comments, "metadata": log.metadata, "ip_address": log.ip_address, "user_agent": log.user_agent,
    }


class AuditLogView(APIView):
    """Everything recorded in the audit trail, newest first. Administrators only; read-only."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        logs = _filtered(request.query_params)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(logs, request)
        response = paginator.get_paginated_response([_row(log) for log in page])
        response.data["actions"] = sorted(AuditLog.objects.order_by().values_list("action", flat=True).distinct())
        return response


class AuditLogExportView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        export_format = request.query_params.get("file_format", "xlsx")
        if export_format not in ("csv", "xlsx"):
            raise ValidationError("Unsupported export format. Use csv or xlsx.")
        logs = list(_filtered(request.query_params)[:10000])
        rows = [
            [timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"), log.actor.display_name if log.actor_id else "System",
             log.action, log.request.number if log.request_id and log.request.number else "", log.message, log.comments,
             log.ip_address or ""]
            for log in logs
        ]
        services.log(request.user, "AUDIT_EXPORTED",
                     f"{request.user.display_name} exported the audit log as {export_format.upper()}",
                     metadata={"rows": len(rows)})
        headers = ["When", "Who", "Action", "Request #", "What happened", "Comments", "IP address"]
        return EXPORTERS[export_format]("Audit Log", headers, rows, f"audit-log-{timezone.localdate():%Y%m%d}")
