from decimal import Decimal

from apps.audit.models import AuditLog
from apps.core.models import SystemConfig
from apps.requests.models import Budget, Request, Vendor

from .base import PortalTestCase


class ControlsTestCase(PortalTestCase):
    def payment(self, user=None, payee="Acme Supplies", amount="5000", invoice="", submit=True, **extra):
        user = user or self.juan
        draft = self.create(user, {
            "request_type": "RFP", "payable_to": payee, "invoice_number": invoice,
            "lines": [{"description": "Office chairs", "amount": amount}], **extra,
        })
        if not submit:
            return draft
        response = self.act(user, draft["id"], "submit")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def detail(self, user, request_id):
        return self.as_user(user).get(f"/api/requests/{request_id}/").data


class DuplicateTests(ControlsTestCase):
    def test_same_payee_and_invoice_is_flagged_whatever_the_amount(self):
        first = self.payment(invoice="INV-100")
        second = self.payment(user=self.sofia, payee="acme supplies ", amount="7250", invoice="inv-100")
        found = self.detail(self.sofia, second["id"])["checks"]["duplicates"]
        self.assertEqual([(d["number"], d["id"]) for d in found], [(first["number"], None)])  # Sofia cannot open Juan's
        self.assertIn("invoice number", found[0]["reason"])
        # Finance verifies both and can open the other one.
        self.assertEqual(str(self.detail(self.fiona, second["id"])["checks"]["duplicates"][0]["id"]), str(first["id"]))
        log = AuditLog.objects.get(request_id=second["id"], action="SUBMITTED")
        self.assertIn(first["number"], log.metadata["possible_duplicates"][0])

    def test_same_payee_and_amount_is_flagged_but_turned_down_requests_are_not(self):
        first = self.payment()
        second = self.payment()
        self.assertEqual(len(self.detail(self.juan, second["id"])["checks"]["duplicates"]), 1)
        self.act(self.maria, first["id"], "reject", comments="Paid already")
        self.assertEqual(self.detail(self.juan, second["id"])["checks"]["duplicates"], [])

    def test_different_payee_or_amount_is_not_a_duplicate(self):
        self.payment()
        self.assertEqual(self.detail(self.juan, self.payment(payee="Other Co")["id"])["checks"]["duplicates"], [])
        self.assertEqual(self.detail(self.juan, self.payment(amount="5001")["id"])["checks"]["duplicates"], [])
        self.assertEqual(self.detail(self.juan, self.submitted_pr()["id"])["checks"]["duplicates"], [])


class VendorTests(ControlsTestCase):
    def test_typing_a_listed_name_links_the_vendor(self):
        vendor = Vendor.objects.create(name="Acme Supplies, Inc.")
        listed = self.payment(payee="  acme supplies, inc. ", submit=False)
        self.assertEqual(Request.objects.get(pk=listed["id"]).vendor, vendor)
        self.assertEqual(listed["payable_to"], "Acme Supplies, Inc.")  # spelled as listed
        self.assertFalse(listed["checks"]["unlisted_payee"])
        other = self.payment(payee="Somebody Else", submit=False)
        self.assertTrue(other["checks"]["unlisted_payee"])
        # Changing the payee re-evaluates the link.
        changed = self.as_user(self.juan).patch(f"/api/requests/{listed['id']}/", {"payable_to": "Somebody Else"}, format="json")
        self.assertIsNone(Request.objects.get(pk=listed["id"]).vendor)
        self.assertTrue(changed.data["checks"]["unlisted_payee"])
        self.assertIn("Acme Supplies, Inc.", self.as_user(self.juan).get("/api/lookups/").data["vendors"])

    def test_only_administrators_keep_the_list_and_used_vendors_cannot_be_deleted(self):
        self.assertEqual(self.as_user(self.juan).get("/api/vendors/").status_code, 403)
        client = self.as_user(self.admin)
        created = client.post("/api/vendors/", {"name": "Acme Supplies", "tin": "123-456"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(client.post("/api/vendors/", {"name": "Acme Supplies"}, format="json").status_code, 400)
        self.payment()
        self.assertEqual(self.as_user(self.admin).delete(f"/api/vendors/{created.data['id']}/").status_code, 400)
        self.assertEqual(self.as_user(self.admin).get("/api/vendors/").data[0]["request_count"], 1)

    def test_payee_report(self):
        Vendor.objects.create(name="Acme Supplies")
        self.payment(amount="5000")
        self.payment(amount="2500", payee="acme supplies")
        self.payment(amount="900", payee="Walk-in Hardware")
        rows = self.as_user(self.fiona).get("/api/reports/").data["by_payee"]
        self.assertEqual([(r["label"], r["count"], Decimal(r["amount"]), r["listed"]) for r in rows],
                         [("Acme Supplies", 2, Decimal("7500"), True), ("Walk-in Hardware", 1, Decimal("900"), False)])


class BudgetTests(ControlsTestCase):
    def setUp(self):
        super().setUp()
        from django.utils import timezone

        self.year = timezone.localdate().year
        self.budget = Budget.objects.create(department=self.it, year=self.year, amount=Decimal("10000"))

    def test_position_counts_submitted_requests_and_not_linked_payments(self):
        pr = self.submitted_pr(unit_cost="3000", quantity="2")  # 6,000
        budget = self.detail(self.maria, pr["id"])["checks"]["budget"]
        self.assertEqual((Decimal(budget["used"]), Decimal(budget["remaining"]), budget["over"]),
                         (Decimal("6000"), Decimal("4000"), False))
        # Paying for that PR does not use the budget a second time.
        self.act(self.maria, pr["id"], "approve")
        linked = self.payment(amount="6000", source_request=pr["id"])
        budget = self.detail(self.maria, linked["id"])["checks"]["budget"]
        self.assertEqual((Decimal(budget["used"]), Decimal(budget["this_request"])), (Decimal("6000"), Decimal("0")))
        # Drafts and rejected requests do not count; another department has no budget.
        self.payment(amount="9000", payee="Draft Co", submit=False)
        rejected = self.payment(amount="9000", payee="Rejected Co")
        self.act(self.maria, rejected["id"], "reject", comments="No")
        self.assertEqual(Decimal(self.as_user(self.admin).get("/api/budgets/").data[0]["used"]), Decimal("6000"))
        self.assertIsNone(self.detail(self.sofia, self.payment(user=self.sofia)["id"])["checks"]["budget"])

    def test_going_over_warns_by_default_and_is_recorded(self):
        over = self.payment(amount="12000")
        self.assertTrue(self.detail(self.maria, over["id"])["checks"]["budget"]["over"])
        # The requester is told it is over budget, without the department's figures.
        self.assertEqual(self.detail(self.juan, over["id"])["checks"]["budget"],
                         {"year": self.year, "department": "IT", "over": True})
        log = AuditLog.objects.get(request_id=over["id"], action="SUBMITTED")
        self.assertIn("over its", log.metadata["over_budget"])

    def test_administrators_can_make_the_budget_a_hard_stop(self):
        SystemConfig.objects.filter(pk=1).update(block_over_budget=True)
        draft = self.payment(amount="12000", submit=False)
        blocked = self.act(self.juan, draft["id"], "submit")
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("budget", blocked.data["errors"])
        Budget.objects.filter(pk=self.budget.pk).update(amount=Decimal("20000"))
        self.assertEqual(self.act(self.juan, draft["id"], "submit").status_code, 200)

    def test_budget_administration(self):
        self.assertEqual(self.as_user(self.juan).get("/api/budgets/").data, [])
        self.assertEqual(len(self.as_user(self.fiona).get("/api/budgets/").data), 1)
        payload = {"department": str(self.sales.id), "year": self.year, "amount": "50000"}
        self.assertEqual(self.as_user(self.fiona).post("/api/budgets/", payload, format="json").status_code, 403)
        self.assertEqual(self.as_user(self.admin).post("/api/budgets/", payload, format="json").status_code, 201)
        self.assertEqual(self.as_user(self.admin).post("/api/budgets/", payload, format="json").status_code, 400)


class VerifiableFormTests(ControlsTestCase):
    def test_printed_form_carries_a_code_that_opens_the_request(self):
        from apps.requests import pdf

        seen = []
        original = pdf.QrCodeWidget

        def spy(value, **kwargs):
            seen.append(value)
            return original(value, **kwargs)

        pdf.QrCodeWidget = spy
        try:
            for request in (self.submitted_pr(), self.payment()):
                response = self.as_user(self.juan).get(f"/api/requests/{request['id']}/pdf/")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(seen[-1].endswith(f"/verify/{request['id']}"))
        finally:
            pdf.QrCodeWidget = original


class AnalyticsTests(ControlsTestCase):
    def test_trend_previous_period_funnel_and_budget_use(self):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        Budget.objects.create(department=self.it, year=today.year, amount=Decimal("10000"))
        first = self.payment(amount="4000")
        self.payment(amount="1000", payee="Other Co")
        self.act(self.maria, first["id"], "approve")
        earlier = self.payment(amount="700", payee="Earlier Co")
        Request.objects.filter(pk=earlier["id"]).update(submitted_at=timezone.now() - timedelta(days=10))

        week = {"date_from": (today - timedelta(days=6)).isoformat(), "date_to": today.isoformat()}
        data = self.as_user(self.fiona).get("/api/reports/", week).data
        self.assertEqual((data["totals"]["requests"], data["previous"]["requests"]), (2, 1))
        self.assertEqual(data["trend"]["unit"], "day")
        self.assertEqual([p["count"] for p in data["trend"]["points"]], [0, 0, 0, 0, 0, 0, 2])
        self.assertEqual((data["funnel"]["submitted"], data["funnel"]["completed"]), (2, 0))
        self.assertEqual(data["by_department"][0]["key"], str(self.it.id))
        self.assertEqual(Decimal(data["budgets"][0]["used"]), Decimal("5700"))

        # Open-ended periods have nothing to compare with; long ones are shown by month.
        everything = self.as_user(self.fiona).get("/api/reports/").data
        self.assertIsNone(everything["previous"])
        year = self.as_user(self.fiona).get("/api/reports/", {"date_from": f"{today.year}-01-01", "date_to": f"{today.year}-12-31"}).data
        self.assertEqual((year["trend"]["unit"], len(year["trend"]["points"])), ("month", 12))
        # Clicking a status bar filters by it; department heads see no budget figures here.
        pending = self.as_user(self.fiona).get("/api/reports/", {"status": "PENDING_APPROVAL"}).data
        self.assertEqual({row["status"] for row in pending["by_status"]}, {"PENDING_APPROVAL"})
        self.assertEqual(self.as_user(self.maria).get("/api/reports/").data["budgets"], [])


class PublicVerificationTests(ControlsTestCase):
    def test_anyone_holding_the_form_can_confirm_it_but_sees_no_detail(self):
        request = self.payment(amount="5000", purpose="Confidential purpose")
        self.act(self.maria, request["id"], "approve")
        self.client.force_authenticate(None)
        response = self.client.get(f"/api/verify/{request['id']}/")
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual((data["number"], Decimal(data["total_amount"]), data["requester_name"]),
                         (request["number"], Decimal("5000"), "Juan Test"))
        signed = [(step["label"], step["actor"], step["state"]) for step in data["steps"]]
        self.assertIn(("Noted By", "Maria Test", "done"), signed)
        self.assertEqual({step["actor"] for step in data["steps"] if step["state"] == "upcoming"}, {""})
        body = str(response.data)
        for private in ("Confidential purpose", "Office chairs", "lines", "attachments", "comments"):
            self.assertNotIn(private, body)

    def test_drafts_and_unknown_codes_are_not_found(self):
        draft = self.payment(submit=False)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/verify/{draft['id']}/").status_code, 404)
        self.assertEqual(self.client.get("/api/verify/00000000-0000-4000-8000-000000000000/").status_code, 404)


class EmailActionTests(ControlsTestCase):
    def test_approval_email_offers_approve_and_return_and_others_do_not(self):
        from django.core import mail

        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            request = self.payment()
        to_approver = next(m for m in mail.outbox if m.to == ["maria@example.com"])
        link = f"/requests/{request['id']}"
        self.assertIn(f"{link}?action=approve", to_approver.body)
        self.assertIn(f"{link}?action=return", to_approver.alternatives[0][0])
        others = [m for m in mail.outbox if m.to != ["maria@example.com"]]
        self.assertTrue(others)
        self.assertTrue(all("?action=" not in m.body for m in others))
