import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.requests.models import Request, RequestType, Vendor
from apps.users.models import Role, User
from apps.workflows.models import ApproverType

from .base import PortalTestCase


class FeatureTestCase(PortalTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        RequestType.objects.filter(code__in=("CA", "LIQ")).update(is_active=True)  # off by default
        cls.ca, cls.liq = (RequestType.objects.get(code=c) for c in ("CA", "LIQ"))
        head = dict(approver_type=ApproverType.DEPARTMENT_HEAD)
        cls.workflow("CA", cls.ca, None, None, [("Department Head", head)])
        cls.workflow("LIQ", cls.liq, None, None, [("Department Head", head)])

    def advance(self, user=None, amount="5000", release=True):
        user = user or self.juan
        draft = self.create(user, {"request_type": "CA", "payable_to": user.display_name,
                                   "lines": [{"description": "Client visit, Cebu", "amount": amount}]})
        submitted = self.act(user, draft["id"], "submit")
        self.assertEqual(submitted.status_code, 200, submitted.data)
        if release:
            self.complete(draft["id"], head=self.maria if user.department_id == self.it.id else self.sergio)
        return self.as_user(user).get(f"/api/requests/{draft['id']}/").data

    def complete(self, request_id, head=None):
        self.assertEqual(self.act(head or self.maria, request_id, "approve").status_code, 200)
        for status in ("OPS_RECEIVED", "PROCESSING", "COMPLETED"):
            response = self.as_user(self.oscar).post(f"/api/requests/{request_id}/ops/status/", {"status": status}, format="json")
            self.assertEqual(response.status_code, 200, response.data)

    def liquidation_payload(self, advance_id, amount="4200"):
        return {"request_type": "LIQ", "source_request": advance_id, "purpose": "Client visit, Cebu",
                "lines": [{"description": "Hotel", "amount": amount, "category": str(self.meals.id),
                           "expense_date": timezone.localdate().isoformat()}]}

    def attach_receipt(self, user, request_id):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .base import PDF_BYTES

        upload = SimpleUploadedFile("receipt.pdf", PDF_BYTES, content_type="application/pdf")
        response = self.as_user(user).post(f"/api/requests/{request_id}/attachments/", {"file": upload, "kind": "RECEIPT"},
                                           format="multipart")
        self.assertEqual(response.status_code, 201, response.data)


class CashAdvanceTests(FeatureTestCase):
    def test_advance_is_liquidated_with_the_balance_worked_out(self):
        advance = self.advance(amount="5000")
        self.assertEqual((advance["advance"]["role"], advance["advance"]["released"], advance["advance"]["liquidated"]),
                         ("advance", True, False))
        offered = self.as_user(self.juan).get("/api/requests/linkable/", {"kind": "advance"}).data
        self.assertEqual([row["number"] for row in offered], [advance["number"]])

        liquidation = self.create(self.juan, self.liquidation_payload(advance["id"], amount="4200"))
        position = liquidation["advance"]
        self.assertEqual((Decimal(position["advance_amount"]), Decimal(position["spent"]),
                          Decimal(position["to_return"]), Decimal(position["to_reimburse"])),
                         (Decimal("5000"), Decimal("4200"), Decimal("800"), Decimal("0")))
        # Once one is being filed the advance is no longer offered, and a second is refused.
        self.assertEqual(self.as_user(self.juan).get("/api/requests/linkable/", {"kind": "advance"}).data, [])
        second = self.as_user(self.juan).post("/api/requests/", self.liquidation_payload(advance["id"]), format="json")
        self.assertEqual(second.status_code, 400)

        self.attach_receipt(self.juan, liquidation["id"])
        self.assertEqual(self.act(self.juan, liquidation["id"], "submit").status_code, 200)
        self.complete(liquidation["id"])
        after = self.as_user(self.juan).get(f"/api/requests/{advance['id']}/").data["advance"]
        self.assertTrue(after["liquidated"])
        self.assertEqual(after["liquidation"]["number"], Request.objects.get(pk=liquidation["id"]).number)
        pdf = self.as_user(self.juan).get(f"/api/requests/{liquidation['id']}/pdf/")
        self.assertEqual(pdf.status_code, 200)

    def test_spending_more_than_the_advance_is_reimbursed(self):
        advance = self.advance(amount="1000")
        position = self.create(self.juan, self.liquidation_payload(advance["id"], amount="1350"))["advance"]
        self.assertEqual((Decimal(position["to_return"]), Decimal(position["to_reimburse"])), (Decimal("0"), Decimal("350")))

    def test_rules_for_what_can_be_liquidated(self):
        mine, theirs = self.advance(), self.advance(user=self.sofia)
        pr = self.submitted_pr()
        post = lambda payload: self.as_user(self.juan).post("/api/requests/", payload, format="json")  # noqa: E731
        self.assertEqual(post(self.liquidation_payload(theirs["id"])).status_code, 400)  # someone else's advance
        self.assertEqual(post(self.liquidation_payload(pr["id"])).status_code, 400)      # not a cash advance
        unapproved = self.advance(release=False)
        self.assertEqual(post(self.liquidation_payload(unapproved["id"])).status_code, 400)
        # A liquidation must name its advance before it can be submitted.
        loose = self.create(self.juan, {**self.liquidation_payload(mine["id"]), "source_request": None})
        self.attach_receipt(self.juan, loose["id"])
        refused = self.act(self.juan, loose["id"], "submit")
        self.assertEqual(refused.status_code, 400)
        self.assertIn("source_request", refused.data["errors"])

    def test_a_new_advance_shows_the_ones_still_outstanding(self):
        first = self.advance()
        second = self.advance(release=False)
        outstanding = self.as_user(self.maria).get(f"/api/requests/{second['id']}/").data["checks"]["open_advances"]
        self.assertEqual([row["number"] for row in outstanding], [first["number"]])


class OnBehalfTests(FeatureTestCase):
    def test_prepared_for_a_colleague_and_only_they_can_submit(self):
        draft = self.create(self.juan, self.pr_payload(requester=str(self.sofia.id)))
        self.assertEqual((draft["requester_name"], draft["prepared_by_name"], draft["department_name"]),
                         ("Sofia Test", "Juan Test", "Sales"))
        self.assertTrue(draft["prepared_for_other"])
        self.assertEqual((draft["permissions"]["can_edit"], draft["permissions"]["can_submit"], draft["permissions"]["can_hand_over"]),
                         (True, False, True))
        self.assertEqual(self.act(self.juan, draft["id"], "submit").status_code, 403)  # it would carry Sofia's signature

        self.assertEqual(self.act(self.juan, draft["id"], "hand-over").status_code, 200)
        self.assertTrue(Notification.objects.filter(recipient=self.sofia, event="PREPARED_FOR_YOU").exists())
        hers = self.as_user(self.sofia).get(f"/api/requests/{draft['id']}/").data["permissions"]
        self.assertEqual((hers["can_submit"], hers["can_hand_over"]), (True, False))
        submitted = self.act(self.sofia, draft["id"], "submit")
        self.assertEqual(submitted.status_code, 200, submitted.data)
        # Her department's head approves, and the preparer can still follow it.
        self.assertEqual(self.act(self.sergio, draft["id"], "approve").status_code, 200)
        self.assertEqual(self.as_user(self.juan).get(f"/api/requests/{draft['id']}/").status_code, 200)

    def test_own_requests_are_unchanged_and_others_cannot_take_over(self):
        own = self.create(self.juan, self.pr_payload())
        self.assertFalse(own["prepared_for_other"])
        self.assertEqual((own["permissions"]["can_submit"], own["permissions"]["can_hand_over"]), (True, False))
        self.assertEqual(self.act(self.juan, own["id"], "hand-over").status_code, 403)
        draft = self.create(self.juan, self.pr_payload(requester=str(self.sofia.id)))
        change = self.as_user(self.sofia).patch(f"/api/requests/{draft['id']}/", {"requester": str(self.maria.id)}, format="json")
        self.assertEqual(change.status_code, 400)  # only the preparer may change who it is for


class PurchaseOrderTests(FeatureTestCase):
    def test_ops_issues_a_numbered_purchase_order_from_an_approved_requisition(self):
        Vendor.objects.create(name="Acme Supplies, Inc.", tin="123-456-789", address="Makati City")
        pr = self.submitted_pr()
        url = f"/api/requests/{pr['id']}/purchase-order/"
        early = self.as_user(self.oscar).post(url, {"supplier": "Acme Supplies, Inc."}, format="json")
        self.assertEqual(early.status_code, 400)  # not approved yet
        self.act(self.maria, pr["id"], "approve")
        self.assertEqual(self.as_user(self.juan).post(url, {"supplier": "Acme"}, format="json").status_code, 403)
        self.assertEqual(self.as_user(self.oscar).get(url).status_code, 400)  # nothing issued yet

        issued = self.as_user(self.oscar).post(url, {"supplier": "acme supplies, inc.", "terms": "30 days"}, format="json")
        self.assertEqual(issued.status_code, 200, issued.data)
        year = timezone.localdate().year
        self.assertEqual((issued.data["po_number"], issued.data["payable_to"], issued.data["po_issued_by_name"]),
                         (f"PO-{year}-000001", "Acme Supplies, Inc.", "Oscar Test"))
        self.assertTrue(AuditLog.objects.filter(request_id=pr["id"], action="PO_ISSUED").exists())
        # Updating keeps the number; the next requisition gets the next one.
        again = self.as_user(self.oscar).post(url, {"supplier": "Other Supplier", "terms": ""}, format="json")
        self.assertEqual((again.data["po_number"], again.data["payable_to"]), (f"PO-{year}-000001", "Other Supplier"))
        other = self.submitted_pr()
        self.act(self.maria, other["id"], "approve")
        second = self.as_user(self.oscar).post(f"/api/requests/{other['id']}/purchase-order/", {"supplier": "Acme"}, format="json")
        self.assertEqual(second.data["po_number"], f"PO-{year}-000002")

        printed = self.as_user(self.juan).get(url)
        self.assertEqual((printed.status_code, printed["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(printed.content.startswith(b"%PDF"))


class BulkApproveTests(FeatureTestCase):
    def test_each_request_is_decided_on_its_own(self):
        first, second = self.submitted_pr(), self.submitted_pr()
        not_mine = self.submitted_pr(user=self.sofia)
        response = self.as_user(self.maria).post("/api/approvals/bulk-approve/", {
            "ids": [first["id"], second["id"], not_mine["id"]], "comments": "Batch"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(response.data["approved"]), sorted([first["number"], second["number"]]))
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertEqual(Request.objects.get(pk=first["id"]).status, "APPROVED")
        self.assertEqual(Request.objects.get(pk=not_mine["id"]).status, "PENDING_APPROVAL")
        self.assertEqual(self.as_user(self.maria).post("/api/approvals/bulk-approve/", {"ids": []}, format="json").status_code, 400)

    def test_no_signature_means_nothing_is_approved(self):
        pr = self.submitted_pr()
        User.objects.filter(pk=self.maria.pk).update(signature="")
        response = self.as_user(User.objects.get(pk=self.maria.pk)).post("/api/approvals/bulk-approve/", {"ids": [pr["id"]]}, format="json")
        self.assertEqual((response.data["approved"], len(response.data["failed"])), ([], 1))
        self.assertIn("signature", response.data["failed"][0]["detail"].lower())


class PasswordResetTests(FeatureTestCase):
    def link(self):
        match = re.search(r"uid=([\w-]+)&token=([\w-]+)", mail.outbox[-1].body)
        return match.group(1), match.group(2)

    def test_local_account_resets_by_emailed_link_once(self):
        self.client.force_authenticate(None)
        mail.outbox.clear()
        unknown = self.client.post("/api/auth/password-reset/", {"email": "nobody@example.com"}, format="json")
        known = self.client.post("/api/auth/password-reset/", {"email": "JUAN@example.com"}, format="json")
        self.assertEqual((unknown.status_code, unknown.data), (known.status_code, known.data))  # no way to tell them apart
        self.assertEqual([m.to for m in mail.outbox], [["juan@example.com"]])
        uid, token = self.link()

        confirm = lambda **data: self.client.post("/api/auth/password-reset/confirm/", data, format="json")  # noqa: E731
        self.assertEqual(confirm(uid=uid, token=token, new_password="short").status_code, 400)
        self.assertEqual(confirm(uid=uid, token="wrong-token", new_password="A-new-long-passphrase-1").status_code, 400)
        self.assertEqual(confirm(uid=uid, token=token, new_password="A-new-long-passphrase-1").status_code, 200)
        self.assertEqual(confirm(uid=uid, token=token, new_password="Another-long-passphrase-2").status_code, 400)  # used
        signed_in = self.client.post("/api/auth/login/", {"email": "juan@example.com", "password": "A-new-long-passphrase-1"}, format="json")
        self.assertEqual(signed_in.status_code, 200)

    def test_windows_accounts_are_told_to_use_windows_and_get_no_link(self):
        User.objects.filter(pk=self.sofia.pk).update(directory_username="sofia")
        self.client.force_authenticate(None)
        mail.outbox.clear()
        self.client.post("/api/auth/password-reset/", {"email": "sofia@example.com"}, format="json")
        self.assertIn("Windows", mail.outbox[-1].body)
        self.assertNotIn("token=", mail.outbox[-1].body)


class DirectoryCoverTests(FeatureTestCase):
    def test_a_colleague_who_never_signed_in_can_be_named_as_cover(self):
        from apps.users.directory import DirectoryEntry

        entry = DirectoryEntry(dn="CN=Nina,OU=IT,DC=x", username="nina", email="nina@example.com", first_name="Nina",
                               last_name="New", position="Analyst", ous=["IT"])
        with mock.patch("apps.users.directory.is_configured", return_value=True), \
             mock.patch("apps.users.directory.search", return_value=[entry]), \
             mock.patch("apps.users.directory.find", return_value=entry):
            portal_only = self.as_user(self.maria).get("/api/colleagues/", {"search": "nin"}).data
            self.assertEqual(portal_only, [])
            found = self.as_user(self.maria).get("/api/colleagues/", {"search": "nin", "directory": "1"}).data
            self.assertEqual([(p["id"], p["directory_username"], p["name"]) for p in found], [(None, "nina", "Nina New")])
            saved = self.as_user(self.maria).put("/api/me/delegation/", {"directory_username": "nina"}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        nina = User.objects.get(directory_username="nina")
        self.assertEqual((saved.data["delegate"]["name"], nina.department, nina.has_usable_password()), ("Nina New", self.it, False))
        self.assertTrue(nina.has_role(Role.REQUESTER))


class ExportAndAuditTests(FeatureTestCase):
    def test_request_list_export_follows_the_filters_and_visibility(self):
        self.submitted_pr()
        self.submitted_pr(user=self.sofia)
        mine = self.as_user(self.juan).get("/api/requests/export/", {"file_format": "csv"})
        self.assertEqual(mine.status_code, 200)
        text = mine.content.decode("utf-8-sig")
        self.assertEqual(len(text.strip().splitlines()), 2)  # header + Juan's own request only
        everything = self.as_user(self.oscar).get("/api/requests/export/", {"file_format": "csv", "type": "PR"})
        self.assertEqual(len(everything.content.decode("utf-8-sig").strip().splitlines()), 3)
        sheet = self.as_user(self.oscar).get("/api/requests/export/")
        self.assertIn("spreadsheetml", sheet["Content-Type"])

    def test_audit_log_is_searchable_by_administrators_only(self):
        pr = self.submitted_pr()
        self.assertEqual(self.as_user(self.oscar).get("/api/audit-log/").status_code, 403)
        client = self.as_user(self.admin)
        by_number = client.get("/api/audit-log/", {"search": pr["number"]}).data
        self.assertTrue(by_number["count"] >= 1)
        self.assertTrue(all(row["request_number"] == pr["number"] for row in by_number["results"]))
        submitted = client.get("/api/audit-log/", {"action": "SUBMITTED"}).data
        self.assertEqual({row["action"] for row in submitted["results"]}, {"SUBMITTED"})
        self.assertIn("SUBMITTED", submitted["actions"])
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.assertEqual(client.get("/api/audit-log/", {"date_from": tomorrow}).data["count"], 0)
        self.assertEqual(client.get("/api/audit-log/export/", {"file_format": "csv"}).status_code, 200)
