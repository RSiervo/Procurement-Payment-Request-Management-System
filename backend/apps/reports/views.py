from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.requests.models import Status

from . import services
from .exporters import EXPORTERS


class ReportFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    type = serializers.CharField(required=False, allow_blank=True)
    department = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(choices=Status.choices, required=False)

    def validate(self, attrs):
        if attrs.get("date_from") and attrs.get("date_to") and attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError({"date_to": "The end date must not be before the start date."})
        return attrs


def _filters(request):
    params = {k: v for k, v in request.query_params.items() if v != ""}
    serializer = ReportFilterSerializer(data=params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class DashboardView(APIView):
    def get(self, request):
        days = request.query_params.get("days", "7")
        return Response(services.dashboard(request.user, int(days) if days in ("7", "14", "30") else 7))


class ReportSummaryView(APIView):
    def get(self, request):
        return Response(services.analytics(request.user, _filters(request)))


class ReportExportView(APIView):
    def get(self, request):
        report = request.query_params.get("report", "")
        export_format = request.query_params.get("file_format", "csv")
        if export_format not in EXPORTERS:
            raise ValidationError("Unsupported export format. Use csv, xlsx or pdf.")
        table = services.export_table(report, services.report_queryset(request.user, _filters(request)))
        if table is None:
            raise ValidationError("Unknown report.")
        title, headers, rows = table
        audit.log(request.user, "REPORT_EXPORTED",
                  f"{request.user.display_name} exported “{title}” as {export_format.upper()}",
                  metadata={"rows": len(rows)})
        filename = f"{report}-{timezone.localdate():%Y%m%d}"
        return EXPORTERS[export_format](title, headers, rows, filename)
