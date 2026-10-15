from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel, UUIDModel


class ApproverType(models.TextChoices):
    DEPARTMENT_HEAD = "DEPARTMENT_HEAD", "Head of the request's department"
    ROLE = "ROLE", "Anyone holding a role"
    USER = "USER", "A specific user"


class Workflow(BaseModel):
    """An approval route plus the rule that decides which requests take it.

    A request matches when its type equals `request_type`, its department equals
    `department` (or `department` is empty) and its amount lies within
    [min_amount, max_amount], both bounds inclusive and optional.
    """

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    request_type = models.ForeignKey("requests.RequestType", on_delete=models.CASCADE, related_name="workflows")
    department = models.ForeignKey(
        "users.Department", null=True, blank=True, on_delete=models.CASCADE, related_name="workflows"
    )
    min_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    priority = models.SmallIntegerField(default=0, help_text="Higher wins when several workflows match.")
    requires_ops_processing = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["request_type__name", "min_amount", "name"]
        indexes = [models.Index(fields=["request_type", "is_active"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(min_amount__isnull=True) | Q(max_amount__isnull=True) | Q(min_amount__lte=F("max_amount")),
                name="workflow_amount_range_valid",
            ),
        ]

    def __str__(self):
        return self.name


class WorkflowStep(UUIDModel):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80, help_text="Shown on the timeline and the printed form.")
    level = models.ForeignKey("users.ApprovalLevel", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approver_type = models.CharField(max_length=20, choices=ApproverType.choices)
    role = models.ForeignKey("users.Role", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    after_ops = models.BooleanField(
        default=False, help_text="Approve after OPS has processed the request (internal and final approvals)."
    )

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["workflow", "order"], name="workflow_step_order_unique"),
            models.CheckConstraint(
                condition=(
                    Q(approver_type="DEPARTMENT_HEAD", role__isnull=True, user__isnull=True)
                    | Q(approver_type="ROLE", role__isnull=False, user__isnull=True)
                    | Q(approver_type="USER", role__isnull=True, user__isnull=False)
                ),
                name="workflow_step_approver_consistent",
            ),
        ]

    def __str__(self):
        return f"{self.workflow.name} / {self.order}. {self.name}"
