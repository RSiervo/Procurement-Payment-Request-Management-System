import os
import secrets

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import SystemConfig
from apps.notifications.defaults import DEFAULT_TEMPLATES
from apps.notifications.models import NotificationTemplate
from apps.requests.models import ExpenseCategory, FormKind, RequestType
from apps.users.models import ApprovalLevel, Role, User

ROLES = [
    (Role.REQUESTER, "Requester", "Creates and tracks their own requests."),
    (Role.APPROVER, "Approver", "Approves requests routed to them."),
    (Role.DEPARTMENT_HEAD, "Department Head", "Approves requests from their department."),
    (Role.FINANCE, "Finance", "Reviews and verifies payment and reimbursement requests."),
    (Role.OPS, "OPS", "Receives and processes approved requests."),
    ("PRESIDENT", "President", "Gives the internal approval that follows OPS processing."),
    (Role.ADMIN, "Administrator", "Manages users, workflows and system configuration."),
]
LEVELS = [("DEPT_HEAD", "Department Head", 1), ("FINANCE", "Finance", 2), ("SENIOR_MGMT", "Senior Management", 3)]
REQUEST_TYPES = [
    (RequestType.PR, "Purchase Requisition", "PR", FormKind.ITEMS, False,
     "Request the purchase of goods or services."),
    (RequestType.RFP, "Request for Payment", "RFP", FormKind.PAYMENT, False,
     "Request payment to a supplier or payee."),
    (RequestType.REIM, "Reimbursement", "REIM", FormKind.EXPENSE, True,
     "Claim back business expenses you paid for."),
    (RequestType.CA, "Cash Advance", "CA", FormKind.PAYMENT, False,
     "Ask for money in advance for an upcoming expense. It must be liquidated afterwards."),
    (RequestType.LIQ, "Liquidation", "LIQ", FormKind.EXPENSE, True,
     "Account for a cash advance with your receipts."),
]
# Built in but not offered until an administrator switches them on.
OPTIONAL_TYPES = (RequestType.CA, RequestType.LIQ)
CATEGORIES = ["Transportation", "Meals", "Accommodation", "Office Supplies", "Communication",
              "Representation", "Training", "Other"]


class Command(BaseCommand):
    help = "Create the reference data the application needs. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email", help="Create an administrator account with this email if missing.")

    @transaction.atomic
    def handle(self, *args, **options):
        for code, name, description in ROLES:
            Role.objects.update_or_create(
                code=code, defaults={"name": name, "description": description, "is_system": True}
            )
        for code, name, rank in LEVELS:
            ApprovalLevel.objects.get_or_create(code=code, defaults={"name": name, "rank": rank})
        for order, (code, name, prefix, kind, needs_file, description) in enumerate(REQUEST_TYPES):
            RequestType.objects.get_or_create(code=code, defaults={
                "name": name, "number_prefix": prefix, "form_kind": kind,
                "requires_attachment": needs_file, "description": description, "sort_order": order,
                # Optional types start switched off; an administrator turns them on under Request Types.
                "is_active": code not in OPTIONAL_TYPES,
            })
        for name in CATEGORIES:
            ExpenseCategory.objects.get_or_create(name=name)
        for event, (subject, body) in DEFAULT_TEMPLATES.items():
            NotificationTemplate.objects.get_or_create(event=event, defaults={"subject": subject, "body": body})
        SystemConfig.load()
        self.stdout.write(self.style.SUCCESS("Reference data is in place."))

        email = options.get("admin_email")
        if email and not User.objects.filter(email=email.lower()).exists():
            password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            admin = User.objects.create_user(email, password, first_name="System", last_name="Administrator",
                                             position="Administrator")
            admin.roles.set(Role.objects.filter(code__in=[Role.ADMIN, Role.REQUESTER]))
            shown = "(from ADMIN_PASSWORD)" if os.environ.get("ADMIN_PASSWORD") else password
            self.stdout.write(self.style.WARNING(f"Administrator created: {email} / password: {shown}"))
            self.stdout.write("Change this password after the first sign-in.")
