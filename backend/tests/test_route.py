from apps.requests.models import Status
from apps.users.models import Role
from apps.workflows.models import ApproverType

from .base import PortalTestCase


class CompanyRouteTests(PortalTestCase):
    """Department Head -> OPS processing -> President -> Finance, whose approval completes the request."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        head = dict(approver_type=ApproverType.DEPARTMENT_HEAD)
        president = dict(approver_type=ApproverType.ROLE, role=Role.objects.get(code="SENIOR"), after_ops=True)
        finance = dict(approver_type=ApproverType.ROLE, role=Role.objects.get(code=Role.FINANCE), after_ops=True)
        # Department-specific, so Sales requests take this route instead of the generic ones.
        cls.workflow("Sales PR", cls.pr, None, None,
                     [("Department Head", head), ("President", president), ("Finance", finance)], department=cls.sales)

    def ops(self, user, request_id, status):
        return self.as_user(user).post(f"/api/requests/{request_id}/ops/status/", {"status": status}, format="json")

    def detail(self, user, request_id):
        return self.as_user(user).get(f"/api/requests/{request_id}/").data

    def through_ops(self):
        pr = self.submitted_pr(user=self.sofia)
        self.assertEqual(self.act(self.sergio, pr["id"], "approve").data["status"], Status.APPROVED)
        for status in (Status.OPS_RECEIVED, Status.PROCESSING):
            self.assertEqual(self.ops(self.oscar, pr["id"], status).status_code, 200)
        return pr

    def test_full_route_ends_with_finance(self):
        pr = self.submitted_pr(user=self.sofia)
        self.assertEqual(pr["status"], Status.PENDING_APPROVAL)

        approved = self.act(self.sergio, pr["id"], "approve").data
        self.assertEqual((approved["status"], approved["current_handler"]), (Status.APPROVED, "OPS"))
        # The President and Finance come after OPS; neither can sign yet.
        self.assertEqual(self.act(self.sam, pr["id"], "approve").status_code, 400)
        self.assertEqual(self.act(self.fiona, pr["id"], "approve").status_code, 400)

        self.ops(self.oscar, pr["id"], Status.OPS_RECEIVED)
        self.ops(self.oscar, pr["id"], Status.PROCESSING)
        offered = [n["status"] for n in self.detail(self.oscar, pr["id"])["permissions"]["next_statuses"]]
        self.assertEqual(offered, [Status.INTERNAL_APPROVAL])
        self.assertEqual(self.ops(self.oscar, pr["id"], Status.COMPLETED).status_code, 400)  # OPS cannot complete it

        sent = self.ops(self.oscar, pr["id"], Status.INTERNAL_APPROVAL).data
        self.assertEqual(sent["status"], Status.INTERNAL_APPROVAL)
        self.assertIn("President", sent["current_handler"])
        self.assertEqual(self.act(self.fiona, pr["id"], "approve").status_code, 403)  # not Finance's turn

        with_finance = self.act(self.sam, pr["id"], "approve").data
        self.assertEqual(with_finance["status"], Status.FOR_FINANCE)
        self.assertEqual(self.ops(self.oscar, pr["id"], Status.COMPLETED).status_code, 400)
        self.assertTrue(self.detail(self.fiona, pr["id"])["permissions"]["can_decide"])

        done = self.act(self.fiona, pr["id"], "approve").data
        self.assertEqual(done["status"], Status.COMPLETED)
        self.assertIsNotNone(done["completed_at"])

        nodes = self.as_user(self.sofia).get(f"/api/requests/{pr['id']}/timeline/").data["current"]
        self.assertEqual([n["label"] for n in nodes],
                         ["Submitted", "Department Head", "OPS", "OPS Processing", "President", "Finance", "Completed"])
        self.assertTrue(all(n["state"] == "done" for n in nodes))

    def test_pending_lists_follow_the_route(self):
        pr = self.through_ops()
        self.assertEqual(self.as_user(self.sam).get("/api/approvals/").data, [])
        self.ops(self.oscar, pr["id"], Status.INTERNAL_APPROVAL)
        self.assertEqual([r["id"] for r in self.as_user(self.sam).get("/api/approvals/").data], [pr["id"]])
        self.assertEqual(self.as_user(self.fiona).get("/api/approvals/").data, [])
        self.act(self.sam, pr["id"], "approve")
        self.assertEqual([r["id"] for r in self.as_user(self.fiona).get("/api/approvals/").data], [pr["id"]])

    def test_return_after_ops_restarts_the_whole_route(self):
        pr = self.through_ops()
        self.ops(self.oscar, pr["id"], Status.INTERNAL_APPROVAL)
        returned = self.act(self.sam, pr["id"], "return", comments="Wrong supplier.").data
        self.assertEqual(returned["status"], Status.RETURNED)

        again = self.act(self.sofia, pr["id"], "submit").data
        self.assertEqual(again["status"], Status.PENDING_APPROVAL)
        self.assertIsNone(again["ops_received_at"])
        self.assertEqual(self.act(self.sergio, pr["id"], "approve").data["status"], Status.APPROVED)
        labels = [n["label"] for n in self.as_user(self.sofia).get(f"/api/requests/{pr['id']}/timeline/").data["current"]]
        self.assertEqual(labels.index("OPS") < labels.index("President") < labels.index("Finance"), True)

    def test_rejection_by_finance_is_final(self):
        pr = self.through_ops()
        self.ops(self.oscar, pr["id"], Status.INTERNAL_APPROVAL)
        self.act(self.sam, pr["id"], "approve")
        rejected = self.act(self.fiona, pr["id"], "reject", comments="Over budget.").data
        self.assertEqual(rejected["status"], Status.REJECTED)

    def test_route_preview_marks_steps_after_ops(self):
        response = self.as_user(self.sofia).post(
            "/api/requests/route-preview/", {"request_type": "PR", "amount": "100"}, format="json")
        self.assertEqual([(s["name"], s["after_ops"]) for s in response.data["route"]["steps"]],
                         [("Department Head", False), ("President", True), ("Finance", True)])

    def test_workflow_steps_after_ops_must_come_last(self):
        finance = str(Role.objects.get(code=Role.FINANCE).id)
        payload = {"name": "Bad order", "request_type": "RFP", "steps": [
            {"name": "Finance", "approver_type": "ROLE", "role": finance, "after_ops": True},
            {"name": "Department Head", "approver_type": "DEPARTMENT_HEAD"},
        ]}
        client = self.as_user(self.admin)
        self.assertEqual(client.post("/api/workflows/", payload, format="json").status_code, 400)
        payload["steps"].reverse()
        created = client.post("/api/workflows/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual([s["after_ops"] for s in created.data["steps"]], [False, True])
