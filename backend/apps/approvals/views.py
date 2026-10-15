from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import SystemConfig
from apps.core.pagination import StandardPagination
from apps.requests import selectors
from apps.requests import services as request_services
from apps.requests.models import Request
from apps.requests.serializers import RequestBriefSerializer, RequestListSerializer

from . import services
from .models import ActionType, ApprovalAction


class PendingApprovalsView(APIView):
    """Requests waiting on the signed-in user, oldest first."""

    def get(self, request):
        steps = (
            services.pending_steps_for(request.user)
            .select_related(
                "instance__request__request_type", "instance__request__requester",
                "instance__request__department", "instance__request__ops_assignee",
            )
            .order_by("activated_at")
        )
        context = {"request": request, "ops_sla_days": SystemConfig.load().ops_sla_days}
        return Response([
            {
                **RequestListSerializer(step.instance.request, context=context).data,
                "step_name": step.name,
                "step_level": step.level_name,
                "pending_since": step.activated_at,
                "needs_clarification": step.needs_clarification,
            }
            for step in steps
        ])


class BulkApproveView(APIView):
    """Approve several waiting requests in one go. Each is decided on its own: one that
    cannot be approved (already decided, no signature...) does not stop the others."""

    def post(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50:
            raise ValidationError({"ids": ["Choose between 1 and 50 requests."]})
        comments = str(request.data.get("comments") or "")[:2000]
        approved, failed = [], []
        for request_id in ids:
            try:
                with transaction.atomic():
                    req = request_services.lock(selectors.visible_to(request.user).get(pk=request_id))
                    services.act(req, request.user, ActionType.APPROVE, comments)
                approved.append(req.number)
            except (Request.DoesNotExist, DjangoValidationError, ValueError):
                failed.append({"number": "", "detail": "This request was not found."})
            except APIException as exc:
                detail = exc.detail
                if isinstance(detail, dict):
                    detail = " ".join(str(m) for messages in detail.values() for m in (messages if isinstance(messages, list) else [messages]))
                elif isinstance(detail, list):
                    detail = " ".join(str(m) for m in detail)
                number = Request.objects.filter(pk=request_id).values_list("number", flat=True).first() or ""
                failed.append({"number": number, "detail": str(detail)})
        return Response({"approved": approved, "failed": failed})


class ApprovalHistoryView(APIView):
    """Decisions the signed-in user has made."""

    def get(self, request):
        actions = (
            ApprovalAction.objects.filter(actor=request.user)
            .select_related("step__instance__request__request_type")
            .order_by("-created_at")
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(actions, request)
        return paginator.get_paginated_response([
            {
                "id": a.id,
                "action": a.action,
                "action_display": a.get_action_display(),
                "comments": a.comments,
                "created_at": a.created_at,
                "step_name": a.step.name,
                "request": RequestBriefSerializer(a.step.instance.request).data,
            }
            for a in page
        ])
