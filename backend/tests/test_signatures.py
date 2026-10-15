import io

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.approvals.models import ApprovalStep
from apps.requests.models import Request, Status
from apps.users.models import User

from .base import PDF_BYTES, PortalTestCase, signature_png


def upload(data, name="signature.png", content_type="image/png"):
    return {"file": SimpleUploadedFile(name, data, content_type=content_type)}


class SignatureTestCase(PortalTestCase):
    @staticmethod
    def without_signature(user):
        """The same person, freshly loaded, with no signature on file."""
        User.objects.filter(pk=user.pk).update(signature="")
        return User.objects.get(pk=user.pk)


class SignatureUploadTests(SignatureTestCase):
    def test_upload_view_replace_and_remove(self):
        client = self.as_user(self.without_signature(self.juan))
        self.assertFalse(client.get("/api/me/").data["has_signature"])
        self.assertEqual(client.get("/api/me/signature/").status_code, 404)

        saved = client.post("/api/me/signature/", upload(signature_png(fmt="JPEG"), "sig.jpg", "image/jpeg"), format="multipart")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertTrue(saved.data["has_signature"])
        image = client.get("/api/me/signature/")
        self.assertEqual(image["Content-Type"], "image/png")  # always stored as a clean PNG
        self.assertTrue(b"".join(image.streaming_content).startswith(b"\x89PNG"))

        self.assertFalse(client.delete("/api/me/signature/").data["has_signature"])

    def test_rejects_files_that_are_not_signature_images(self):
        client = self.as_user(self.juan)
        for label, data in (("pdf renamed to png", PDF_BYTES), ("text", b"not an image"),
                            ("tiny image", signature_png(size=(10, 5))), ("too large", b"\x89PNG" + b"0" * (2 * 1024 * 1024))):
            with self.subTest(label):
                response = client.post("/api/me/signature/", upload(data), format="multipart")
                self.assertEqual(response.status_code, 400)
                self.assertIn("file", response.data["errors"])
        self.assertEqual(client.post("/api/me/signature/", {}, format="multipart").status_code, 400)

    def test_large_pictures_are_scaled_down(self):
        client = self.as_user(self.juan)
        client.post("/api/me/signature/", upload(signature_png(size=(2400, 900))), format="multipart")
        from PIL import Image
        stored = Image.open(io.BytesIO(b"".join(client.get("/api/me/signature/").streaming_content)))
        self.assertLessEqual(stored.width, 600)
        self.assertLessEqual(stored.height, 240)


class SigningTests(SignatureTestCase):
    def test_submitting_and_approving_need_a_signature(self):
        draft = self.create(self.juan, self.pr_payload())
        juan = self.without_signature(self.juan)
        blocked = self.act(juan, draft["id"], "submit")
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("signature", blocked.data["errors"])

        self.as_user(juan).post("/api/me/signature/", upload(signature_png()), format="multipart")
        self.assertEqual(self.act(User.objects.get(pk=juan.pk), draft["id"], "submit").status_code, 200)

        maria = self.without_signature(self.maria)
        unsigned = self.act(maria, draft["id"], "approve")
        self.assertEqual(unsigned.status_code, 400)
        self.assertIn("signature", unsigned.data["errors"])
        # Returning or rejecting does not put a signature on the form, so neither needs one.
        self.assertEqual(self.act(maria, draft["id"], "return", comments="Please add a quotation.").status_code, 200)

    def test_each_record_keeps_the_signature_used_at_the_time(self):
        pr = self.submitted_pr()
        self.act(self.maria, pr["id"], "approve")
        request = Request.objects.get(pk=pr["id"])
        step = ApprovalStep.objects.get(instance__request=request, acted_by=self.maria)
        self.assertTrue(request.requester_signature)
        self.assertTrue(step.signature)
        kept = step.signature.read()

        # Maria replaces her signature afterwards; the approved form keeps the old one.
        self.as_user(self.maria).post("/api/me/signature/", upload(signature_png(size=(300, 120))), format="multipart")
        step.refresh_from_db()
        self.assertEqual(step.signature.read(), kept)
        self.assertNotEqual(User.objects.get(pk=self.maria.pk).signature.read(), kept)

    def test_signatures_are_drawn_on_the_printed_form(self):
        pr = self.submitted_pr()
        unsigned_size = None
        Request.objects.filter(pk=pr["id"]).update(requester_signature="")
        unsigned_size = len(self.as_user(self.juan).get(f"/api/requests/{pr['id']}/pdf/").content)

        signed = self.submitted_pr()
        self.act(self.maria, signed["id"], "approve")
        self.assertEqual(Request.objects.get(pk=signed["id"]).status, Status.APPROVED)
        pdf = self.as_user(self.juan).get(f"/api/requests/{signed['id']}/pdf/").content
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(b"/Subtype /Image", pdf)
        self.assertGreater(len(pdf), unsigned_size)