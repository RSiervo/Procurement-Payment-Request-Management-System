from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.approvals import services as approvals
from apps.users.models import Department, Role, User

from . import controls, services
from .models import (
    AWAITING_APPROVAL, FINAL_STATUSES, OPS_STATUSES, Attachment, AttachmentKind, Budget, Comment, ExpenseCategory, Priority,
    Request, RequestLine, RequestType, Status, Vendor,
)
from .validators import INLINE_TYPES


class RequestTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequestType
        fields = ["id", "code", "name", "description", "number_prefix", "form_kind", "requires_attachment", "is_active"]
        read_only_fields = ["code", "number_prefix", "form_kind"]


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "is_active"]


class VendorSerializer(serializers.ModelSerializer):
    request_count = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = ["id", "name", "tin", "address", "is_active", "request_count"]

    def get_request_count(self, obj):
        return obj.requests.exclude(status=Status.DRAFT).count()


class BudgetSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    used = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = ["id", "department", "department_name", "year", "amount", "used"]

    def get_used(self, obj):
        return controls.committed_amount(obj.department_id, obj.year)

    def validate_year(self, value):
        if not 2000 <= value <= 2100:
            raise serializers.ValidationError("Enter a four-digit year.")
        return value

    def validate_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("The budget cannot be negative.")
        return value


class LineSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")

    class Meta:
        model = RequestLine
        fields = ["id", "position", "description", "remarks", "quantity", "unit_cost", "amount",
                  "expense_date", "category", "category_name"]


class LineWriteSerializer(serializers.Serializer):
    """Shape and range checks only; completeness is enforced when the request is submitted."""

    description = serializers.CharField(max_length=500, allow_blank=True, default="")
    remarks = serializers.CharField(max_length=500, allow_blank=True, default="")
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                        required=False, allow_null=True)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"),
                                         required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"),
                                      required=False, allow_null=True)
    expense_date = serializers.DateField(required=False, allow_null=True)
    category = serializers.PrimaryKeyRelatedField(queryset=ExpenseCategory.objects.filter(is_active=True),
                                                  required=False, allow_null=True)


class RequestWriteSerializer(serializers.Serializer):
    request_type = serializers.SlugRelatedField(slug_field="code", required=False,
                                                queryset=RequestType.objects.filter(is_active=True))
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.filter(is_active=True),
                                                    required=False, allow_null=True)
    # Set when preparing the request for a colleague; left out, the request is the signed-in person's own.
    requester = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True),
                                                   required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=Priority.choices, required=False)
    purpose = serializers.CharField(allow_blank=True, max_length=4000, required=False)
    date_needed = serializers.DateField(required=False, allow_null=True)
    payable_to = serializers.CharField(allow_blank=True, max_length=200, required=False)
    source_request = serializers.PrimaryKeyRelatedField(queryset=Request.objects.all(), required=False, allow_null=True)
    pr_reference = serializers.CharField(allow_blank=True, max_length=40, required=False)
    po_number = serializers.CharField(allow_blank=True, max_length=40, required=False)
    rr_number = serializers.CharField(allow_blank=True, max_length=40, required=False)
    invoice_number = serializers.CharField(allow_blank=True, max_length=40, required=False)
    posted = serializers.BooleanField(required=False, allow_null=True)
    lines = LineWriteSerializer(many=True, required=False)

    def validate_lines(self, lines):
        if len(lines) > 200:
            raise serializers.ValidationError("A request can have at most 200 lines.")
        return lines

    def validate(self, attrs):
        if self.instance is None and "request_type" not in attrs:
            raise serializers.ValidationError({"request_type": "Request type is required."})
        if self.instance is not None:
            attrs.pop("request_type", None)  # the type of an existing request never changes
        return attrs


class OpsUpdateSerializer(serializers.Serializer):
    ops_assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True),
                                                      required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=Priority.choices, required=False)
    po_number = serializers.CharField(allow_blank=True, max_length=40, required=False)
    rr_number = serializers.CharField(allow_blank=True, max_length=40, required=False)
    invoice_number = serializers.CharField(allow_blank=True, max_length=40, required=False)
    posted = serializers.BooleanField(required=False, allow_null=True)


class PurchaseOrderSerializer(serializers.Serializer):
    supplier = serializers.CharField(max_length=200)
    terms = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")


class OpsStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[s for s in Status.choices if s[0] in services.OPS_TARGETS])
    remarks = serializers.CharField(allow_blank=True, max_length=2000, required=False, default="")


class DecisionSerializer(serializers.Serializer):
    comments = serializers.CharField(allow_blank=True, max_length=2000, required=False, default="")


class RoutePreviewSerializer(serializers.Serializer):
    request_type = serializers.SlugRelatedField(slug_field="code", queryset=RequestType.objects.filter(is_active=True))
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all(), required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.display_name", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    previewable = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ["id", "original_name", "content_type", "size", "kind", "kind_display",
                  "uploaded_by_name", "created_at", "previewable", "can_delete"]

    def get_previewable(self, obj):
        return obj.content_type in INLINE_TYPES

    def get_can_delete(self, obj):
        user = self.context["request"].user
        return obj.uploaded_by_id == user.pk and services.can_attach(user, obj.request)


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    kind = serializers.ChoiceField(choices=AttachmentKind.choices, default=AttachmentKind.OTHER)


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.display_name", read_only=True)
    author_position = serializers.CharField(source="author.position", read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "body", "author_name", "author_position", "created_at"]


class RequestBriefSerializer(serializers.ModelSerializer):
    number = serializers.CharField(source="display_number")
    type_code = serializers.CharField(source="request_type.code")
    type_name = serializers.CharField(source="request_type.name")
    status_display = serializers.CharField(source="get_status_display")

    class Meta:
        model = Request
        fields = ["id", "number", "type_code", "type_name", "status", "status_display", "total_amount"]


class RequestListSerializer(serializers.ModelSerializer):
    number = serializers.CharField(source="display_number")
    type_code = serializers.CharField(source="request_type.code")
    type_name = serializers.CharField(source="request_type.name")
    form_kind = serializers.CharField(source="request_type.form_kind")
    status_display = serializers.CharField(source="get_status_display")
    requester_name = serializers.CharField(source="requester.display_name")
    department_name = serializers.CharField(source="department.name")
    ops_assignee_name = serializers.CharField(source="ops_assignee.display_name", default="")
    is_overdue = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Request
        fields = [
            "id", "number", "type_code", "type_name", "form_kind", "status", "status_display", "priority", "summary",
            "requester_name", "department", "department_name", "total_amount", "current_handler",
            "date_needed", "ops_assignee", "ops_assignee_name", "is_overdue",
            "submitted_at", "approved_at", "completed_at", "created_at", "updated_at",
        ]

    def get_summary(self, obj):
        """First line's description, with "+N more" when there are several lines."""
        if hasattr(obj, "first_line"):
            first, count = obj.first_line, obj.line_count or 0
        else:  # not loaded through selectors.with_summary
            descriptions = list(obj.lines.values_list("description", flat=True))
            first, count = (descriptions[0] if descriptions else None), len(descriptions)
        if not first:
            return ""
        return f"{first} +{count - 1} more" if count > 1 else first

    def get_is_overdue(self, obj):
        if obj.status in FINAL_STATUSES or obj.status == Status.DRAFT:
            return False
        if obj.date_needed and obj.date_needed < timezone.localdate():
            return True
        sla_days = self.context.get("ops_sla_days", 5)
        return bool(
            obj.status in OPS_STATUSES and obj.approved_at
            and (timezone.now() - obj.approved_at).days >= sla_days
        )


class RequestDetailSerializer(RequestListSerializer):
    lines = LineSerializer(many=True)
    attachments = AttachmentSerializer(many=True)
    requester_position = serializers.CharField(source="requester.position")
    prepared_by_name = serializers.CharField(source="prepared_by.display_name")
    source_request = RequestBriefSerializer()
    linked_requests = serializers.SerializerMethodField()
    current_step = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    checks = serializers.SerializerMethodField()
    advance = serializers.SerializerMethodField()
    requester_id = serializers.UUIDField(read_only=True)
    prepared_for_other = serializers.SerializerMethodField()
    po_issued_by_name = serializers.CharField(source="po_issued_by.display_name", default="")

    class Meta(RequestListSerializer.Meta):
        fields = RequestListSerializer.Meta.fields + [
            "purpose", "payable_to", "pr_reference", "po_number", "rr_number", "invoice_number", "posted",
            "revision", "requester_position", "prepared_by_name", "ops_received_at",
            "lines", "attachments", "source_request", "linked_requests", "current_step", "permissions",
            "checks", "advance", "requester_id", "prepared_for_other", "po_date", "po_terms", "po_issued_by_name",
        ]

    def get_advance(self, obj):
        return controls.advance_position(obj)

    def get_prepared_for_other(self, obj):
        return obj.prepared_by_id != obj.requester_id

    def get_checks(self, obj):
        user = self.context["request"].user
        step = self._step(obj)
        can_decide = bool(step and obj.status in AWAITING_APPROVAL and approvals.can_act(user, step, obj))
        return controls.summary(user, obj, can_decide=can_decide)

    def _step(self, obj):
        if not hasattr(obj, "_current_step"):
            obj._current_step = approvals.current_step(obj)
        return obj._current_step

    def get_linked_requests(self, obj):
        user = self.context["request"].user
        from .selectors import visible_to

        linked = visible_to(user).filter(source_request=obj).select_related("request_type")
        return RequestBriefSerializer(linked, many=True).data

    def get_current_step(self, obj):
        step = self._step(obj)
        if step is None:
            return None
        return {"name": step.name, "level": step.level_name, "needs_clarification": step.needs_clarification,
                "pending_since": step.activated_at}

    def get_permissions(self, obj):
        user = self.context["request"].user
        owner = services.is_owner(user, obj)
        step = self._step(obj)
        next_statuses = [
            {"status": status, "label": Status(status).label}
            for status, roles in services.next_ops_statuses(obj).items()
            if user.has_role(*roles)
        ]
        return {
            "is_owner": owner,
            "can_edit": owner and obj.is_editable,
            # Submitting applies the requester's signature, so only they can do it.
            "can_submit": obj.is_editable and user.pk == obj.requester_id,
            "can_hand_over": obj.is_editable and user.pk == obj.prepared_by_id and user.pk != obj.requester_id,
            "can_issue_po": services.can_issue_po(user, obj),
            "can_delete": owner and obj.status == Status.DRAFT and obj.revision == 0,
            "can_cancel": (owner or user.has_role(Role.ADMIN))
                          and obj.status in (Status.PENDING_APPROVAL, Status.RETURNED),
            "can_decide": bool(step and obj.status in AWAITING_APPROVAL and approvals.can_act(user, step, obj)),
            "can_attach": services.can_attach(user, obj),
            "can_update_processing": obj.status in OPS_STATUSES and user.has_role(Role.OPS),
            "next_statuses": next_statuses,
        }
