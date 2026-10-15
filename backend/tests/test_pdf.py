import re

from .base import PortalTestCase


def sheets(pdf):
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))


class PrintedFormTests(PortalTestCase):
    def pdf(self, user, request_id):
        response = self.as_user(user).get(f"/api/requests/{request_id}/pdf/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))
        return response.content

    def test_requisition_fits_one_half_sheet_and_long_ones_continue(self):
        short = self.submitted_pr()
        self.assertEqual(sheets(self.pdf(self.juan, short["id"])), 1)
        long = self.create(self.juan, {"request_type": "PR", "lines": [
            {"quantity": "1", "description": f"Item {n}", "remarks": "Stock"} for n in range(20)]})
        self.assertEqual(sheets(self.pdf(self.juan, long["id"])), 3)  # eight ruled rows per sheet

    def test_payment_form_is_used_for_payments_and_reimbursements(self):
        for payload in (
            {"request_type": "RFP", "payable_to": "Acme Supply", "lines": [{"description": "Toner", "amount": "1500"}]},
            {"request_type": "REIM", "purpose": "Client visit", "lines": [
                {"description": "Taxi", "amount": "500", "expense_date": "2026-01-05",
                 "category": str(self.meals.id)}]},
        ):
            with self.subTest(type=payload["request_type"]):
                created = self.create(self.juan, payload)
                self.assertEqual(sheets(self.pdf(self.juan, created["id"])), 1)