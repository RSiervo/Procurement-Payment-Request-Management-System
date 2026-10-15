from decimal import Decimal

from django.core import mail

from apps.approvals.models import ApprovalInstance
from apps.audit.models import AuditLog
from apps.notifications.models import Event, Notification
from apps.requests.models import Request, Status
from apps.workflows.models import ApproverType
from apps.workflows.services import resolve_workflow

from .base import PortalTestCase


class WorkflowResolutionTests(PortalTestCase):
    def test_amount_tiers_select_the_matching_workflow(self):
        cases = [("0", self.wf_small), ("9999.99", self.wf_small), ("10000", self.wf_mid),
                 ("50000", self.wf_mid), ("50000.01", self.wf_large)]
        for amount, expected in cases:
            with self.subTest(amount=amount):
                self.assertEqual(resolve_workflow(self.pr, self.it, Decimal(amount)), expected)

    def test_department_specific_workflow_beats_the_generic_one(self):
        special = self.workflow("Sales PR", self.pr, None, None,
                                [("Sales Head", dict(approver_type=ApproverType.DEPARTMENT_HEAD))],
                                department=self.sales)
        self.assertEqual(resolve_workflow(self.pr, self.sales, Decimal("100")), special)
        self.assertEqual(resolve_workflow(self.pr, self.it, Decimal("100")), self.wf_small)

    def test_inactive_workflow_is_ignored_and_submission_is_blocked(self):
        self.wf_small.is_active = False
        self.wf_small.save()
        draft = self.create(self.juan, self.pr_payload(unit_cost="100"))
        response = self.act(self.juan, draft["id"], "submit")
        self.assertEqual(response.status_code, 400)
        self.assertIn("No approval workflow", response.data["detail"])
        self.assertEqual(Request.objects.get(pk=draft["id"]).status, Status.DRAFT)


class ApprovalLifecycleTests(PortalTestCase):
    def test_full_lifecycle_from_submission_to_completion(self):
        with self.captureOnCommitCallbacks(execute=True):
            pr = self.submitted_pr(unit_cost="12000")  # 24,000 -> head, then finance
        self.assertRegex(pr["number"], r"^PR-\d{4}-000001$")
        self.assertEqual(pr["status"], Status.PENDING_APPROVAL)
        self.assertIn("Maria", pr["current_handler"])
        self.assertTrue(Notification.objects.filter(recipient=self.maria, event=Event.APPROVAL_REQUIRED).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.oscar, event=Event.REQUEST_SUBMITTED).exists())
        self.assertEqual({m.to[0] for m in mail.outbox}, {self.maria.email, self.oscar.email})
        self.assertIn(pr["number"], mail.outbox[0].subject)

        self.assertEqual(self.act(self.maria, pr["id"], "approve").data["current_handler"], "Finance")
        approved = self.act(self.fiona, pr["id"], "approve", comments="Budget confirmed").data
        self.assertEqual(approved["status"], Status.APPROVED)
        self.assertEqual(approved["current_handler"], "OPS")
        self.assertTrue(Notification.objects.filter(recipient=self.oscar, event=Event.OPS_ACTION_REQUIRED).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.juan, event=Event.REQUEST_APPROVED).exists())

        for status in (Status.OPS_RECEIVED, Status.PROCESSING, Status.COMPLETED):
            response = self.act(self.oscar, pr["id"], "ops/status", status=status, remarks="ok")
            self.assertEqual(response.status_code, 200, response.data)
        done = Request.objects.get(pk=pr["id"])
        self.assertEqual(done.status, Status.COMPLETED)
        self.assertIsNotNone(done.completed_at)

        actions = list(AuditLog.objects.filter(request=done).order_by("created_at").values_list("action", flat=True))
        for expected in ("CREATED", "SUBMITTED", "APPROVED", "FULLY_APPROVED", "OPS_RECEIVED", "COMPLETED"):
            self.assertIn(expected, actions)
        timeline = self.as_user(self.juan).get(f"/api/requests/{pr['id']}/timeline/").data
        self.assertTrue(all(node["state"] == "done" for node in timeline["current"]))

    def test_requester_cannot_approve_their_own_request(self):
        pr = self.submitted_pr(user=self.maria, unit_cost="12000")  # her own head step is skipped
        response = self.act(self.maria, pr["id"], "approve")
        self.assertEqual(response.status_code, 403)
        self.assertIn("your own request", response.data["detail"])

    def test_department_head_step_is_skipped_when_the_head_is_the_requester(self):
        pr = self.submitted_pr(user=self.maria, unit_cost="12000")
        self.assertEqual(pr["current_handler"], "Finance")
        timeline = self.as_user(self.maria).get(f"/api/requests/{pr['id']}/timeline/").data
        self.assertEqual(timeline["current"][1]["state"], "skipped")

    def test_submission_is_blocked_when_no_independent_approver_exists(self):
        draft = self.create(self.maria, self.pr_payload(unit_cost="100"))  # only step: her own
        response = self.act(self.maria, draft["id"], "submit")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Request.objects.get(pk=draft["id"]).status, Status.DRAFT)
        self.assertIsNone(Request.objects.get(pk=draft["id"]).number)

    def test_only_the_current_approver_may_decide(self):
        pr = self.submitted_pr(unit_cost="12000")
        for outsider in (self.fiona, self.sergio, self.oscar, self.admin):
            with self.subTest(user=outsider.email):
                self.assertIn(self.act(outsider, pr["id"], "approve").status_code, (403, 404))
        self.assertEqual(Request.objects.get(pk=pr["id"]).status, Status.PENDING_APPROVAL)

    def test_reject_and_return_require_a_reason(self):
        pr = self.submitted_pr()
        for action in ("reject", "return", "clarify"):
            response = self.act(self.maria, pr["id"], action)
            self.assertEqual(response.status_code, 400)
            self.assertIn("comments", response.data["errors"])

    def test_rejected_request_is_final(self):
        pr = self.submitted_pr()
        self.assertEqual(self.act(self.maria, pr["id"], "reject", comments="No budget").data["status"], Status.REJECTED)
        self.assertEqual(self.as_user(self.juan).patch(f"/api/requests/{pr['id']}/", {"purpose": "x"},
                                                       format="json").status_code, 400)
        self.assertEqual(self.act(self.juan, pr["id"], "submit").status_code, 400)
        note = Notification.objects.get(recipient=self.juan, event=Event.REQUEST_REJECTED)
        self.assertIn("No budget", note.message)

    def test_return_edit_resubmit_keeps_history_and_number(self):
        pr = self.submitted_pr()
        returned = self.act(self.maria, pr["id"], "return", comments="Add the model").data
        self.assertEqual(returned["status"], Status.RETURNED)
        self.assertFalse(returned["permissions"]["can_edit"])  # the approver cannot edit it
        mine = self.as_user(self.juan).get(f"/api/requests/{pr['id']}/").data
        self.assertTrue(mine["permissions"]["can_edit"])

        edit = self.as_user(self.juan).patch(f"/api/requests/{pr['id']}/", {"purpose": "ThinkPad T14"}, format="json")
        self.assertEqual(edit.status_code, 200)
        again = self.act(self.juan, pr["id"], "submit").data
        self.assertEqual(again["number"], pr["number"])
        self.assertEqual(again["status"], Status.PENDING_APPROVAL)
        self.assertEqual(ApprovalInstance.objects.filter(request_id=pr["id"]).count(), 2)

        timeline = self.as_user(self.juan).get(f"/api/requests/{pr['id']}/timeline/").data
        self.assertEqual(len(timeline["previous"]), 1)
        self.assertEqual(timeline["previous"][0]["nodes"][1]["comments"], "Add the model")
        self.assertTrue(AuditLog.objects.filter(request_id=pr["id"], action="RESUBMITTED").exists())

    def test_pending_request_cannot_be_edited(self):
        pr = self.submitted_pr()
        response = self.as_user(self.juan).patch(f"/api/requests/{pr['id']}/", {"purpose": "changed"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_clarification_keeps_the_step_pending_and_notifies_the_requester(self):
        pr = self.submitted_pr()
        response = self.act(self.maria, pr["id"], "clarify", comments="Which model?")
        self.assertEqual(response.data["status"], Status.PENDING_APPROVAL)
        self.assertTrue(response.data["current_step"]["needs_clarification"])
        self.assertTrue(Notification.objects.filter(recipient=self.juan, event=Event.CLARIFICATION_REQUESTED).exists())
        self.as_user(self.juan).post(f"/api/requests/{pr['id']}/comments/", {"body": "T14"}, format="json")
        detail = self.as_user(self.maria).get(f"/api/requests/{pr['id']}/").data
        self.assertFalse(detail["current_step"]["needs_clarification"])
        self.assertTrue(Notification.objects.filter(recipient=self.maria, event=Event.COMMENT_ADDED).exists())

    def test_editing_a_workflow_does_not_change_requests_in_flight(self):
        pr = self.submitted_pr(unit_cost="12000")
        self.wf_mid.steps.filter(order=2).delete()
        self.assertEqual(self.act(self.maria, pr["id"], "approve").data["current_handler"], "Finance")

    def test_ops_cannot_skip_states_and_only_ops_can_process(self):
        pr = self.submitted_pr()
        self.act(self.maria, pr["id"], "approve")
        self.assertEqual(self.act(self.oscar, pr["id"], "ops/status", status=Status.COMPLETED).status_code, 400)
        self.assertEqual(self.act(self.juan, pr["id"], "ops/status", status=Status.OPS_RECEIVED).status_code, 403)
        self.assertEqual(self.act(self.oscar, pr["id"], "ops/status", status=Status.OPS_RECEIVED).status_code, 200)

    def test_cancel_closes_the_approval_cycle(self):
        pr = self.submitted_pr()
        self.assertEqual(self.act(self.juan, pr["id"], "cancel").data["status"], Status.CANCELLED)
        self.assertEqual(self.act(self.maria, pr["id"], "approve").status_code, 400)
        approvals = self.as_user(self.maria).get("/api/approvals/").data
        self.assertEqual(approvals, [])
