import io
import os
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas

from apps.approvals import services as approvals
from apps.approvals.models import ActionType
from apps.core.models import SystemConfig
from apps.requests import services as requests
from apps.requests.models import ExpenseCategory, Request, RequestType, Status
from apps.users.models import ApprovalLevel, Department, Role, User
from apps.workflows.models import ApproverType, Workflow, WorkflowStep

DEPARTMENTS = [("IT", "Information Technology"), ("FIN", "Finance"), ("OPS", "Operations"),
               ("HR", "Human Resources"), ("SALES", "Sales")]
# email prefix, first, last, position, department, roles
USERS = [
    ("admin", "Ana", "Reyes", "System Administrator", "IT", [Role.ADMIN, Role.REQUESTER]),
    ("juan", "Juan", "Dela Cruz", "IT Support Specialist", "IT", [Role.REQUESTER]),
    ("maria", "Maria", "Santos", "IT Manager", "IT", [Role.DEPARTMENT_HEAD, Role.APPROVER, Role.REQUESTER]),
    ("fiona", "Fiona", "Garcia", "Finance Manager", "FIN", [Role.FINANCE, Role.DEPARTMENT_HEAD, Role.REQUESTER]),
    ("felix", "Felix", "Lim", "Accountant", "FIN", [Role.FINANCE, Role.REQUESTER]),
    ("oscar", "Oscar", "Mendoza", "Operations Supervisor", "OPS", [Role.OPS, Role.DEPARTMENT_HEAD, Role.REQUESTER]),
    ("olivia", "Olivia", "Tan", "Operations Officer", "OPS", [Role.OPS, Role.REQUESTER]),
    ("sam", "Samuel", "Cruz", "General Manager", "OPS", ["SENIOR_MANAGEMENT", Role.APPROVER]),
    ("hannah", "Hannah", "Ramos", "HR Manager", "HR", [Role.DEPARTMENT_HEAD, Role.REQUESTER]),
    ("sofia", "Sofia", "Villanueva", "Sales Executive", "SALES", [Role.REQUESTER]),
    ("sergio", "Sergio", "Aquino", "Sales Manager", "SALES", [Role.DEPARTMENT_HEAD, Role.REQUESTER]),
]
HEADS = {"IT": "maria", "FIN": "fiona", "OPS": "oscar", "HR": "hannah", "SALES": "sergio"}
HEAD, FIN, SENIOR = "head", "finance", "senior"
# The company route: Department Head, then OPS processing, then the President and Finance.
# Steps are (label, approver, approves after OPS processing).
ROUTE = [("Department Head", HEAD, False), ("President", SENIOR, True), ("Finance", FIN, True)]
# name, type, min, max, steps
WORKFLOWS = [
    ("Purchase Requisition", "PR", None, None, ROUTE),
    ("Request for Payment", "RFP", None, None, ROUTE),
    ("Reimbursement", "REIM", None, None, ROUTE),
]


def _sample_pdf(text):
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    page.drawString(72, 760, text)
    page.save()
    return buffer.getvalue()


def _sample_signature(name):
    """A stand-in e-signature for a demo user: their name in slanted script with a flourish."""
    image = Image.new("RGBA", (420, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\segoesc.ttf", 54)
    except OSError:
        font = ImageFont.load_default()
    draw.text((14, 26), name, font=font, fill=(18, 40, 110, 255))
    draw.line([(10, 122), (150, 112), (300, 126), (410, 104)], fill=(18, 40, 110, 255), width=3)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class Command(BaseCommand):
    help = "Load demo departments, users, workflows and sample requests. For development only."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Password for all demo users (default: DEMO_PASSWORD or random).")
        parser.add_argument("--domain", default="demo.local")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True.")
        if User.objects.filter(email__endswith="@" + options["domain"]).exists():
            raise CommandError("Demo data is already loaded.")
        password = options["password"] or os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(9)
        # Seeding replays dozens of workflow actions; do not spam real mailboxes.
        settings.EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

        call_command("bootstrap", stdout=self.stdout)
        with transaction.atomic():
            self.users = self._people(options["domain"], password)
            self._workflows()
            self._requests()
        config = SystemConfig.load()
        if config.company_name == "Your Company, Inc.":
            config.company_name, config.company_address = "Acme Trading Corporation", "Makati City, Metro Manila"
            config.save()
        self.stdout.write(self.style.SUCCESS(f"Demo data loaded. All demo users share the password: {password}"))
        for prefix, first, last, position, *_ in USERS:
            self.stdout.write(f"  {prefix}@{options['domain']:<12} {first} {last} — {position}")

    def _people(self, domain, password):
        Role.objects.get_or_create(code="SENIOR_MANAGEMENT", defaults={
            "name": "President", "description": "The President: internal approval after OPS processing."})
        departments = {code: Department.objects.get_or_create(code=code, defaults={"name": name})[0]
                       for code, name in DEPARTMENTS}
        levels = {level.code: level for level in ApprovalLevel.objects.all()}
        users = {}
        for prefix, first, last, position, dept, roles in USERS:
            user = User.objects.create_user(f"{prefix}@{domain}", password, first_name=first, last_name=last,
                                            position=position, department=departments[dept])
            user.roles.set(Role.objects.filter(code__in=roles))
            user.signature.save(f"{prefix}.png", ContentFile(_sample_signature(f"{first} {last}")), save=True)
            users[prefix] = user
        for code, prefix in HEADS.items():
            departments[code].head = users[prefix]
            departments[code].save()
            users[prefix].approver_level = levels.get("DEPT_HEAD")
            users[prefix].save()
        users["sam"].approver_level = levels.get("SENIOR_MGMT")
        users["sam"].save()
        return users

    def _workflows(self):
        levels = {level.code: level for level in ApprovalLevel.objects.all()}
        finance = Role.objects.get(code=Role.FINANCE)
        senior = Role.objects.get(code="SENIOR_MANAGEMENT")
        approver = {
            HEAD: dict(approver_type=ApproverType.DEPARTMENT_HEAD, level=levels.get("DEPT_HEAD")),
            FIN: dict(approver_type=ApproverType.ROLE, role=finance, level=levels.get("FINANCE")),
            SENIOR: dict(approver_type=ApproverType.ROLE, role=senior, level=levels.get("SENIOR_MGMT")),
        }
        for name, type_code, low, high, steps in WORKFLOWS:
            workflow = Workflow.objects.create(
                name=name, request_type=RequestType.objects.get(code=type_code),
                min_amount=Decimal(low) if low else None, max_amount=Decimal(high) if high else None,
            )
            for order, (label, who, after_ops) in enumerate(steps, start=1):
                WorkflowStep.objects.create(workflow=workflow, order=order, name=label, after_ops=after_ops,
                                            **approver[who])

    # -- sample requests, driven through the real services so the audit trail is genuine --
    def _draft(self, who, type_code, lines, **header):
        data = {"request_type": RequestType.objects.get(code=type_code), "lines": lines, **header}
        return requests.save_draft(self.users[who], data)

    def _approve(self, req, *approvers):
        for who in approvers:
            approvals.act(Request.objects.get(pk=req.pk), self.users[who], ActionType.APPROVE, "")

    def _requests(self):
        u, today = self.users, timezone.localdate()
        item = lambda qty, desc, remarks, cost: {  # noqa: E731
            "quantity": Decimal(qty), "description": desc, "remarks": remarks, "unit_cost": Decimal(cost)}

        # 1. Completed PR, then an RFP linked to it that is waiting for Finance.
        laptops = self._draft("juan", "PR", [item(2, "Laptop, 14-inch, 16GB RAM", "For new employees", "22500")],
                              date_needed=today + timedelta(days=10), purpose="Equipment for two new hires.")
        requests.submit(u["juan"], laptops)
        self._approve(laptops, "maria")
        for status in (Status.OPS_RECEIVED, Status.PROCESSING, Status.INTERNAL_APPROVAL):
            requests.ops_transition(u["oscar"], laptops, status, "Purchase order issued." if status == Status.PROCESSING else "")
        self._approve(laptops, "sam", "fiona")  # Finance signs last, which completes it
        payment = self._draft(
            "juan", "RFP", [{"description": "2 × Laptop, 14-inch, 16GB RAM", "amount": Decimal("45000")}],
            payable_to="TechSource Computer Trading", source_request=Request.objects.get(pk=laptops.pk),
            invoice_number="INV-88213", posted=False, purpose="Payment for delivered laptops.")
        requests.submit(u["juan"], payment)
        self._approve(payment, "maria")
        for status in (Status.OPS_RECEIVED, Status.PROCESSING, Status.INTERNAL_APPROVAL):
            requests.ops_transition(u["olivia"], payment, status, "")
        self._approve(payment, "sam")  # now waiting for Finance

        # 2. PR approved by the department head, waiting for OPS.
        cables = self._draft("juan", "PR", [
            item(5, "Cat6 network cable, 305m box", "Office infrastructure", "4200"),
            item(2, "24-port gigabit switch", "Third-floor expansion", "8900"),
        ], date_needed=today + timedelta(days=14), purpose="Network expansion for the third floor.")
        requests.submit(u["juan"], cables)
        self._approve(cables, "maria")

        # 3. Small PR waiting on the department head; one approved and waiting for OPS.
        toner = self._draft("juan", "PR", [item(4, "Printer toner cartridge", "Monthly consumables", "1850")],
                            date_needed=today + timedelta(days=5))
        requests.submit(u["juan"], toner)
        chairs = self._draft("sofia", "PR", [item(3, "Ergonomic office chair", "Replacement of broken units", "2950")],
                             date_needed=today + timedelta(days=7))
        requests.submit(u["sofia"], chairs)
        self._approve(chairs, "sergio")

        # 4. Reimbursements: one returned, one in approval.
        category = {c.name: c for c in ExpenseCategory.objects.all()}
        expense = lambda days, cat, desc, amount: {  # noqa: E731
            "expense_date": today - timedelta(days=days), "category": category[cat],
            "description": desc, "amount": Decimal(amount)}
        receipt = lambda name: SimpleUploadedFile(name, _sample_pdf("Sample receipt (demo data)"))  # noqa: E731

        visit = self._draft("sofia", "REIM", [expense(6, "Transportation", "Client visit — taxi", "500"),
                                              expense(5, "Meals", "Client meeting lunch", "850")],
                            purpose="Client visit to Northwind Traders.")
        requests.add_attachment(u["sofia"], visit, receipt("receipts-client-visit.pdf"), "RECEIPT")
        requests.submit(u["sofia"], visit)
        approvals.act(Request.objects.get(pk=visit.pk), u["sergio"], ActionType.RETURN,
                      "The lunch receipt is missing. Please attach it and resubmit.")

        training = self._draft("juan", "REIM", [expense(3, "Training", "Network security workshop fee", "3500")],
                               purpose="Approved external training.")
        requests.add_attachment(u["juan"], training, receipt("workshop-receipt.pdf"), "RECEIPT")
        requests.submit(u["juan"], training)

        # 5. A rejected PR and an unsent draft.
        tablet = self._draft("juan", "PR", [item(1, "Tablet, 11-inch", "For field inventory", "38000")],
                             date_needed=today + timedelta(days=20))
        requests.submit(u["juan"], tablet)
        approvals.act(Request.objects.get(pk=tablet.pk), u["maria"], ActionType.REJECT,
                      "Not in this quarter's budget. Please raise again in Q1.")
        self._draft("juan", "PR", [item(10, "USB-C docking station", "Hot-desk area", "4500")])
