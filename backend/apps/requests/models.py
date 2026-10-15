import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel, TimeStampedModel, UUIDModel


class FormKind(models.TextChoices):
    """Which line-item layout a request type uses."""

    ITEMS = "ITEMS", "Items (quantity, description, remarks)"
    PAYMENT = "PAYMENT", "Payment particulars (particulars, amount)"
    EXPENSE = "EXPENSE", "Expenses (date, category, description, amount)"


class RequestType(UUIDModel, TimeStampedModel):
    PR = "PR"
    RFP = "RFP"
    REIM = "REIM"
    CA = "CA"      # cash advance: money released before the expense
    LIQ = "LIQ"    # liquidation: the receipts that account for a cash advance

    code = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True)
    number_prefix = models.CharField(max_length=10)
    form_kind = models.CharField(max_length=10, choices=FormKind.choices)
    requires_attachment = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class NumberSequence(models.Model):
    """Per-type, per-year counter. Rows are locked while a number is issued."""

    request_type = models.ForeignKey(RequestType, on_delete=models.CASCADE, related_name="+")
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["request_type", "year"], name="number_sequence_unique")]


class ExpenseCategory(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "expense categories"

    def __str__(self):
        return self.name


class Vendor(UUIDModel, TimeStampedModel):
    """A payee the company deals with. Typing a listed name on a request links it to the vendor."""

    name = models.CharField(max_length=200, unique=True)
    tin = models.CharField("TIN", max_length=30, blank=True)
    address = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Budget(UUIDModel, TimeStampedModel):
    """What a department may commit in a calendar year."""

    department = models.ForeignKey("users.Department", on_delete=models.CASCADE, related_name="budgets")
    year = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["-year", "department__name"]
        constraints = [
            models.UniqueConstraint(fields=["department", "year"], name="budget_department_year_unique"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="budget_amount_non_negative"),
        ]

    def __str__(self):
        return f"{self.department} {self.year}"


class Status(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
    RETURNED = "RETURNED", "Returned for Revision"
    REJECTED = "REJECTED", "Rejected"
    APPROVED = "APPROVED", "Approved"
    OPS_RECEIVED = "OPS_RECEIVED", "Received by OPS"
    PROCESSING = "PROCESSING", "Processing"
    INTERNAL_APPROVAL = "INTERNAL_APPROVAL", "Internal Approval"
    FOR_FINANCE = "FOR_FINANCE", "For Finance"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


EDITABLE_STATUSES = (Status.DRAFT, Status.RETURNED)
FINAL_STATUSES = (Status.COMPLETED, Status.REJECTED, Status.CANCELLED)
# Everything between the first approvals and completion: OPS processing, then the
# internal approvals that follow it (ending with Finance).
OPS_STATUSES = (Status.APPROVED, Status.OPS_RECEIVED, Status.PROCESSING, Status.INTERNAL_APPROVAL, Status.FOR_FINANCE)
# Statuses in which an approval step may be waiting for a decision.
AWAITING_APPROVAL = (Status.PENDING_APPROVAL, Status.INTERNAL_APPROVAL, Status.FOR_FINANCE)


class Priority(models.TextChoices):
    LOW = "LOW", "Low"
    NORMAL = "NORMAL", "Normal"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class Request(BaseModel):
    """Common header shared by every request type (PR, RFP, reimbursement, ...)."""

    number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    request_type = models.ForeignKey(RequestType, on_delete=models.PROTECT, related_name="requests")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requests")
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prepared_requests")
    department = models.ForeignKey("users.Department", on_delete=models.PROTECT, related_name="requests")

    purpose = models.TextField(blank=True)
    date_needed = models.DateField(null=True, blank=True)
    payable_to = models.CharField(max_length=200, blank=True)
    # Set by the service layer when payable_to names a listed vendor.
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.PROTECT, related_name="requests")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Document relationships and paper-form reference numbers.
    source_request = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="linked_requests"
    )
    pr_reference = models.CharField(max_length=40, blank=True, help_text="PR number when it is not in this system.")
    po_number = models.CharField(max_length=40, blank=True)
    # Set when OPS issues a purchase order from an approved requisition.
    po_date = models.DateField(null=True, blank=True)
    po_terms = models.CharField(max_length=300, blank=True)
    po_issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    rr_number = models.CharField(max_length=40, blank=True)
    invoice_number = models.CharField(max_length=40, blank=True)
    posted = models.BooleanField(null=True, blank=True)

    # Denormalised "who has it now" so lists never need to walk the approval tables.
    current_handler = models.CharField(max_length=160, blank=True)
    revision = models.PositiveSmallIntegerField(default=0, help_text="Number of times submitted.")

    ops_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="ops_assignments"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    ops_received_at = models.DateTimeField(null=True, blank=True)
    ops_processed_at = models.DateTimeField(null=True, blank=True)
    ops_alerted_at = models.DateTimeField(null=True, blank=True)  # when OPS was told this is overdue
    # The requester's e-signature as it was when the request was (last) submitted.
    requester_signature = models.ImageField(upload_to="signatures/requests/", blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["requester", "status"]),
            models.Index(fields=["request_type", "status"]),
            models.Index(fields=["department", "status"]),
            models.Index(fields=["submitted_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="request_total_non_negative"),
            models.CheckConstraint(
                condition=Q(status="DRAFT") | Q(number__isnull=False), name="request_number_set_once_submitted"
            ),
        ]

    def __str__(self):
        return self.number or f"Draft {self.request_type.code}"

    @property
    def display_number(self):
        return self.number or "Draft"

    @property
    def is_editable(self):
        return self.status in EDITABLE_STATUSES


class RequestLine(UUIDModel):
    """One line table for all form kinds; the service layer enforces which columns apply."""

    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=0)
    description = models.CharField(max_length=500)
    remarks = models.CharField(max_length=500, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expense_date = models.DateField(null=True, blank=True)
    category = models.ForeignKey(ExpenseCategory, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__isnull=True) | Q(quantity__gt=0), name="line_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_cost__isnull=True) | Q(unit_cost__gte=0), name="line_unit_cost_non_negative"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="line_amount_non_negative"),
        ]


class AttachmentKind(models.TextChoices):
    QUOTATION = "QUOTATION", "Quotation"
    SPECIFICATION = "SPECIFICATION", "Specification"
    VENDOR = "VENDOR", "Vendor document"
    RECEIPT = "RECEIPT", "Receipt"
    INVOICE = "INVOICE", "Invoice"
    IMAGE = "IMAGE", "Image"
    OTHER = "OTHER", "Other"


def attachment_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"attachments/{instance.request_id}/{uuid.uuid4().hex}{ext}"


class Attachment(UUIDModel):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path, max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    size = models.PositiveIntegerField()
    kind = models.CharField(max_length=20, choices=AttachmentKind.choices, default=AttachmentKind.OTHER)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Comment(UUIDModel):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
