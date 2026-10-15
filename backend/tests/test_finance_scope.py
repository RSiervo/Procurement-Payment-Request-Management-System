from .base import PortalTestCase


class FinanceScopeTests(PortalTestCase):
    """Finance approves what is routed to it; OPS processing is not its job."""

    def test_finance_has_no_part_in_ops_processing(self):
        pr = self.submitted_pr()
        self.assertEqual(self.act(self.maria, pr["id"], "approve").status_code, 200)  # now with OPS

        finance = self.as_user(self.fiona)
        self.assertIsNone(finance.get("/api/dashboard/").data["ops"])
        detail = finance.get(f"/api/requests/{pr['id']}/").data
        self.assertFalse(detail["permissions"]["can_update_processing"])
        self.assertFalse(detail["permissions"]["can_attach"])
        self.assertEqual(detail["permissions"]["next_statuses"], [])
        self.assertEqual(finance.patch(f"/api/requests/{pr['id']}/ops/", {"po_number": "PO-1"}, format="json").status_code, 403)
        self.assertEqual(finance.post(f"/api/requests/{pr['id']}/ops/status/", {"status": "OPS_RECEIVED"}, format="json").status_code, 403)

        ops = self.as_user(self.oscar)
        self.assertIsNotNone(ops.get("/api/dashboard/").data["ops"])
        self.assertEqual(ops.patch(f"/api/requests/{pr['id']}/ops/", {"po_number": "PO-1"}, format="json").status_code, 200)