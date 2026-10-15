from .base import PortalTestCase


class ActivityTests(PortalTestCase):
    def test_monthly_activity_counts_every_request_in_the_month(self):
        for _ in range(3):
            self.submitted_pr()
        activity = self.as_user(self.juan).get("/api/dashboard/").data["activity"]
        self.assertEqual(len(activity), 6)
        self.assertEqual(activity[-1]["count"], 3)
        self.assertEqual(sum(month["count"] for month in activity), 3)

    def test_dashboard_overview_splits_the_last_week_by_type(self):
        self.submitted_pr()
        self.submitted_pr()
        data = self.as_user(self.juan).get("/api/dashboard/").data
        self.assertEqual(len(data["overview"]), 7)
        nothing_else = {"RFP": 0, "REIM": 0}  # cash advance and liquidation are switched off by default
        self.assertEqual(data["overview"][-1]["counts"], {"PR": 2, **nothing_else})
        self.assertEqual(sum(day["counts"]["PR"] for day in data["overview"]), 2)
        self.assertEqual({row["code"]: row["count"] for row in data["by_type"]}, {"PR": 2, **nothing_else})
        # Another department's requester sees none of them.
        other = self.as_user(self.sofia).get("/api/dashboard/").data
        self.assertEqual(sum(row["count"] for row in other["by_type"]), 0)

    def test_dashboard_period_and_insights(self):
        self.submitted_pr()
        client = self.as_user(self.juan)
        self.assertEqual(len(client.get("/api/dashboard/?days=30").data["overview"]), 30)
        self.assertEqual(len(client.get("/api/dashboard/?days=999").data["overview"]), 7)
        insights = client.get("/api/dashboard/").data["insights"]
        self.assertEqual(insights["created"], {"current": 1, "previous": 0})
        self.assertEqual(insights["completed"], {"current": 0, "previous": 0})
        self.assertEqual(insights["pending_over_3_days"], 0)

    def test_list_rows_carry_a_one_line_summary(self):
        self.create(self.juan, {"request_type": "PR", "lines": [
            {"quantity": "2", "description": "Laptop"}, {"quantity": "1", "description": "Mouse"}]})
        single = self.submitted_pr()
        rows = {row["id"]: row["summary"] for row in self.as_user(self.juan).get("/api/requests/").data["results"]}
        self.assertEqual(rows[single["id"]], "Laptop")
        self.assertIn("Laptop +1 more", rows.values())
        self.act(self.maria, single["id"], "approve")
        self.assertEqual(self.as_user(self.maria).get("/api/approvals/").data, [])
