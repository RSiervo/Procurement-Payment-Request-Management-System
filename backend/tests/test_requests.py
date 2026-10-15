from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.requests.models import Attachment, Request, Status

from .base import PDF_BYTES, PortalTestCase


class DraftAndValidationTests(PortalTestCase):
    def test_draft_is_created_from_the_signed_in_user_and_totals_are_computed(self):
        draft = self.create(self.juan, self.pr_payload(unit_cost="1500.50", quantity="3"))
        self.assertEqual(draft["number"], "Draft")
        self.assertEqual(draft["requester_name"], "Juan Test")
        self.assertEqual(draft["department_name"], "IT")
        self.assertEqual(draft["total_amount"], "4501.50")

    def test_submit_reports_every_missing_field(self):
        draft = self.create(self.juan, {"request_type": "PR", "lines": []})
        response = self.act(self.juan, draft["id"], "submit")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"]["date_needed"], ["Date Needed is required."])
        self.assertEqual(response.data["errors"]["lines"], ["At least one item is required."])

    def test_negative_and_zero_values_are_rejected_by_the_api(self):
        response = self.as_user(self.juan).post(
            "/api/requests/", self.pr_payload(quantity="0"), format="json")
        self.assertEqual(response.status_code, 400)
        response = self.as_user(self.juan).post("/api/requests/", {
            "request_type": "RFP", "lines": [{"description": "Fee", "amount": "-5"}]}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_past_date_needed_is_rejected_on_submit(self):
        payload = self.pr_payload(date_needed=(timezone.localdate() - timedelta(days=1)).isoformat())
        draft = self.create(self.juan, payload)
        response = self.act(self.juan, draft["id"], "submit")
        self.assertIn("date_needed", response.data["errors"])

    def test_reimbursement_requires_a_receipt(self):
        draft = self.create(self.juan, {
            "request_type": "REIM", "purpose": "Client lunch",
            "lines": [{"expense_date": timezone.localdate().isoformat(), "category": str(self.meals.id),
                       "description": "Lunch", "amount": "850"}],
        })
        self.assertEqual(draft["payable_to"], "Juan Test")
        response = self.act(self.juan, draft["id"], "submit")
        self.assertIn("attachments", response.data["errors"])

        upload = self.as_user(self.juan).post(
            f"/api/requests/{draft['id']}/attachments/",
            {"file": SimpleUploadedFile("receipt.pdf", PDF_BYTES), "kind": "RECEIPT"}, format="multipart")
        self.assertEqual(upload.status_code, 201, upload.data)
        submitted = self.act(self.juan, draft["id"], "submit")
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.assertRegex(submitted.data["number"], r"^REIM-\d{4}-000001$")

    def test_numbers_are_sequential_per_type(self):
        first, second = self.submitted_pr(), self.submitted_pr()
        self.assertTrue(first["number"].endswith("000001"))
        self.assertTrue(second["number"].endswith("000002"))

    def test_draft_can_be_deleted_but_submitted_request_cannot(self):
        draft = self.create(self.juan, self.pr_payload())
        self.assertEqual(self.as_user(self.juan).delete(f"/api/requests/{draft['id']}/").status_code, 204)
        pr = self.submitted_pr()
        self.assertEqual(self.as_user(self.juan).delete(f"/api/requests/{pr['id']}/").status_code, 400)


class LinkingTests(PortalTestCase):
    def test_rfp_can_link_to_an_approved_pr_only(self):
        pr = self.submitted_pr()
        payload = {"request_type": "RFP", "payable_to": "Vendor", "source_request": pr["id"],
                   "lines": [{"description": "2 x Laptop", "amount": "3000"}]}
        response = self.as_user(self.juan).post("/api/requests/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("source_request", response.data["errors"])

        self.act(self.maria, pr["id"], "approve")
        linkable = self.as_user(self.juan).get("/api/requests/linkable/").data
        self.assertEqual([row["number"] for row in linkable], [pr["number"]])
        self.assertEqual(linkable[0]["lines"][0]["description"], "2 × Laptop")

        rfp = self.create(self.juan, payload)
        self.assertEqual(rfp["source_request"]["number"], pr["number"])
        detail = self.as_user(self.juan).get(f"/api/requests/{pr['id']}/").data
        self.assertEqual([r["id"] for r in detail["linked_requests"]], [rfp["id"]])

    def test_cannot_link_to_a_pr_the_user_cannot_see(self):
        pr = self.submitted_pr(user=self.sofia)
        self.act(self.sergio, pr["id"], "approve")
        payload = {"request_type": "RFP", "source_request": pr["id"], "lines": []}
        response = self.as_user(self.juan).post("/api/requests/", payload, format="json")
        self.assertEqual(response.status_code, 400)


class VisibilityTests(PortalTestCase):
    def test_requests_are_only_visible_to_the_people_involved(self):
        pr = self.submitted_pr(unit_cost="12000")
        url = f"/api/requests/{pr['id']}/"
        expected = {self.juan: 200, self.maria: 200, self.fiona: 200, self.oscar: 200, self.admin: 200,
                    self.sofia: 404, self.sergio: 404, self.sam: 404}
        for user, status in expected.items():
            with self.subTest(user=user.email):
                self.assertEqual(self.as_user(user).get(url).status_code, status)

    def test_drafts_are_private_to_their_owner(self):
        draft = self.create(self.juan, self.pr_payload())
        for user in (self.maria, self.oscar, self.fiona):
            self.assertEqual(self.as_user(user).get(f"/api/requests/{draft['id']}/").status_code, 404)
        self.assertEqual(self.as_user(self.admin).get(f"/api/requests/{draft['id']}/").status_code, 200)

    def test_list_scopes(self):
        self.create(self.juan, self.pr_payload())
        pr = self.submitted_pr()
        self.submitted_pr(user=self.sofia)
        client = self.as_user(self.juan)
        self.assertEqual(client.get("/api/requests/?scope=mine").data["count"], 2)
        self.assertEqual(client.get("/api/requests/?scope=drafts").data["count"], 1)
        self.assertEqual(client.get(f"/api/requests/?search={pr['number']}").data["count"], 1)
        self.assertEqual(client.get("/api/requests/?status=PENDING_APPROVAL,REJECTED").data["count"], 1)
        awaiting = self.as_user(self.maria).get("/api/requests/?scope=awaiting_me").data
        self.assertEqual([r["id"] for r in awaiting["results"]], [pr["id"]])

    def test_anonymous_access_is_denied(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/requests/").status_code, 403)


class AttachmentTests(PortalTestCase):
    def upload(self, user, request_id, name, content):
        return self.as_user(user).post(f"/api/requests/{request_id}/attachments/",
                                       {"file": SimpleUploadedFile(name, content)}, format="multipart")

    def test_file_type_signature_and_size_are_validated(self):
        draft = self.create(self.juan, self.pr_payload())
        self.assertEqual(self.upload(self.juan, draft["id"], "run.exe", b"MZ....").status_code, 400)
        self.assertEqual(self.upload(self.juan, draft["id"], "fake.pdf", b"<script>alert(1)</script>").status_code, 400)
        self.assertEqual(self.upload(self.juan, draft["id"], "page.html", b"<html>").status_code, 400)
        ok = self.upload(self.juan, draft["id"], "..\\..\\quote.pdf", PDF_BYTES)
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(ok.data["original_name"], "quote.pdf")
        stored = Attachment.objects.get(pk=ok.data["id"])
        self.assertTrue(stored.file.name.startswith(f"attachments/{draft['id']}/"))
        self.assertNotIn("quote", stored.file.name)

    def test_download_follows_request_visibility(self):
        draft = self.create(self.juan, self.pr_payload())
        attachment = self.upload(self.juan, draft["id"], "quote.pdf", PDF_BYTES).data
        url = f"/api/requests/{draft['id']}/attachments/{attachment['id']}/"
        self.assertEqual(self.as_user(self.sofia).get(url).status_code, 404)
        response = self.as_user(self.juan).get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PDF_BYTES)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_documents_are_locked_once_submitted(self):
        pr = self.submitted_pr()
        self.assertEqual(self.upload(self.juan, pr["id"], "late.pdf", PDF_BYTES).status_code, 403)
        self.act(self.maria, pr["id"], "approve")
        self.assertEqual(self.upload(self.oscar, pr["id"], "po.pdf", PDF_BYTES).status_code, 201)


class PdfTests(PortalTestCase):
    def test_pdf_is_generated_for_each_request_type(self):
        pr = self.submitted_pr()
        self.act(self.maria, pr["id"], "approve")
        rfp = self.create(self.juan, {"request_type": "RFP", "payable_to": "Vendor & Sons <Ltd>",
                                      "source_request": pr["id"], "invoice_number": "INV-1", "posted": True,
                                      "lines": [{"description": "2 x Laptop", "amount": "3000"}]})
        reim = self.create(self.juan, {"request_type": "REIM", "purpose": "Trip", "lines": [
            {"expense_date": timezone.localdate().isoformat(), "category": str(self.meals.id),
             "description": "Lunch", "amount": "850"}]})
        for request_id in (pr["id"], rfp["id"], reim["id"]):
            response = self.as_user(self.juan).get(f"/api/requests/{request_id}/pdf/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(Request.objects.get(pk=pr["id"]).status, Status.APPROVED)
