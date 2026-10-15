import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image, ImageDraw
from rest_framework.test import APITestCase

from apps.requests.models import ExpenseCategory, RequestType
from apps.users.models import Department, Role, User
from apps.workflows.models import ApproverType, Workflow, WorkflowStep

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def signature_png(size=(200, 80), fmt="PNG"):
    """A small stand-in signature image."""
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).line([(10, 60), (60, 20), (110, 60), (190, 25)], fill="navy", width=4)
    out = io.BytesIO()
    image.save(out, format=fmt)
    return out.getvalue()
_MEDIA = tempfile.mkdtemp(prefix="ppms-test-media-")


@override_settings(MEDIA_ROOT=_MEDIA)
class PortalTestCase(APITestCase):
    """Small organisation: IT (head Maria) and Sales (head Sergio), Finance, OPS, an admin."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap", stdout=io.StringIO())
        cls.it = Department.objects.create(code="IT", name="IT")
        cls.sales = Department.objects.create(code="SALES", name="Sales")
        Role.objects.create(code="SENIOR", name="Senior Management")

        def user(name, department, *roles):
            u = User.objects.create_user(f"{name}@example.com", "S3cure-pass-phrase", first_name=name.title(),
                                         last_name="Test", position=f"{name.title()} position", department=department)
            u.roles.set(Role.objects.filter(code__in=roles))
            u.signature.save(f"{name}.png", ContentFile(signature_png()), save=True)
            return u

        cls.juan = user("juan", cls.it, Role.REQUESTER)
        cls.maria = user("maria", cls.it, Role.DEPARTMENT_HEAD)
        cls.sofia = user("sofia", cls.sales, Role.REQUESTER)
        cls.sergio = user("sergio", cls.sales, Role.DEPARTMENT_HEAD)
        cls.fiona = user("fiona", cls.it, Role.FINANCE)
        cls.oscar = user("oscar", cls.it, Role.OPS)
        cls.sam = user("sam", cls.it, "SENIOR")
        cls.admin = user("admin", cls.it, Role.ADMIN)
        cls.it.head, cls.sales.head = cls.maria, cls.sergio
        cls.it.save()
        cls.sales.save()

        cls.pr, cls.rfp, cls.reim = (RequestType.objects.get(code=c) for c in ("PR", "RFP", "REIM"))
        head = dict(approver_type=ApproverType.DEPARTMENT_HEAD)
        finance = dict(approver_type=ApproverType.ROLE, role=Role.objects.get(code=Role.FINANCE))
        senior = dict(approver_type=ApproverType.ROLE, role=Role.objects.get(code="SENIOR"))
        cls.wf_small = cls.workflow("PR small", cls.pr, None, "9999.99", [("Department Head", head)])
        cls.wf_mid = cls.workflow("PR mid", cls.pr, "10000", "50000", [("Department Head", head), ("Finance", finance)])
        cls.wf_large = cls.workflow("PR large", cls.pr, "50000.01", None,
                                    [("Department Head", head), ("Finance", finance), ("Senior", senior)])
        cls.workflow("RFP", cls.rfp, None, None, [("Noted By", head), ("Verified By", finance)])
        cls.workflow("REIM", cls.reim, None, None, [("Department Head", head), ("Finance", finance)])
        cls.meals = ExpenseCategory.objects.get(name="Meals")

    @staticmethod
    def workflow(name, request_type, low, high, steps, **extra):
        wf = Workflow.objects.create(name=name, request_type=request_type,
                                     min_amount=Decimal(low) if low else None,
                                     max_amount=Decimal(high) if high else None, **extra)
        for order, (label, approver) in enumerate(steps, start=1):
            WorkflowStep.objects.create(workflow=wf, order=order, name=label, **approver)
        return wf

    def setUp(self):
        cache.clear()  # the sign-in rate limit counts across tests otherwise
        # The database is rolled back between tests but files are not: put back any
        # signature image an earlier test replaced or removed.
        for user in User.objects.exclude(signature=""):
            if not user.signature.storage.exists(user.signature.name):
                user.signature.storage.save(user.signature.name, ContentFile(signature_png()))

    # -- helpers --
    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def pr_payload(self, unit_cost="1500", quantity="2", **extra):
        return {
            "request_type": "PR",
            "date_needed": (timezone.localdate() + timedelta(days=7)).isoformat(),
            "lines": [{"quantity": quantity, "description": "Laptop", "remarks": "New hire", "unit_cost": unit_cost}],
            **extra,
        }

    def create(self, user, payload):
        response = self.as_user(user).post("/api/requests/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def act(self, user, request_id, action, **data):
        return self.as_user(user).post(f"/api/requests/{request_id}/{action}/", data, format="json")

    def submitted_pr(self, user=None, **kwargs):
        user = user or self.juan
        draft = self.create(user, self.pr_payload(**kwargs))
        response = self.act(user, draft["id"], "submit")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data
