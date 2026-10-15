from datetime import timedelta
from unittest import mock

from django.core import mail
from django.utils import timezone

from apps.approvals.models import ApprovalStep
from apps.automation import jobs, runner
from apps.automation.models import JobState
from apps.core.models import SystemConfig
from apps.notifications.models import Notification
from apps.requests.models import Request, Status
from apps.users.models import User

from .base import PortalTestCase


def age_step(request_id, days):
    """Pretend the request reached its current approver this many days ago."""
    ApprovalStep.objects.filter(instance__request_id=request_id, status="PENDING").update(
        activated_at=timezone.now() - timedelta(days=days)
    )


class ApprovalChasingTests(PortalTestCase):
    def test_reminder_goes_out_once_per_period(self):
        pr = self.submitted_pr()
        now = timezone.now()
        self.assertEqual(jobs.approval_reminders(now), "0 reminders sent.")  # only just arrived
        age_step(pr["id"], days=3)
        self.assertEqual(jobs.approval_reminders(now), "1 reminder sent.")
        self.assertTrue(Notification.objects.filter(recipient=self.maria, event="APPROVAL_REMINDER").exists())
        self.assertEqual(jobs.approval_reminders(now + timedelta(hours=1)), "0 reminders sent.")
        self.assertEqual(jobs.approval_reminders(now + timedelta(days=2, hours=1)), "1 reminder sent.")
        # Once decided, nobody is chased any more.
        self.act(self.maria, pr["id"], "approve")
        self.assertEqual(jobs.approval_reminders(now + timedelta(days=9)), "0 reminders sent.")

    def test_escalation_tells_administrators_once(self):
        pr = self.submitted_pr()
        age_step(pr["id"], days=6)
        self.assertEqual(jobs.approval_escalation(timezone.now()), "1 request escalated to the administrators.")
        self.assertTrue(Notification.objects.filter(recipient=self.admin, event="APPROVAL_ESCALATED").exists())
        self.assertFalse(Notification.objects.filter(recipient=self.maria, event="APPROVAL_ESCALATED").exists())
        self.assertEqual(jobs.approval_escalation(timezone.now()), "0 requests escalated to the administrators.")

    def test_zero_days_switches_chasing_off(self):
        SystemConfig.objects.filter(pk=1).update(reminder_after_days=0, escalate_after_days=0)
        for job in (jobs.approval_reminders, jobs.approval_escalation):
            with self.assertRaises(jobs.Skipped):
                job(timezone.now())

    def test_ops_is_alerted_once_about_overdue_processing(self):
        pr = self.submitted_pr()
        self.act(self.maria, pr["id"], "approve")
        self.assertEqual(jobs.ops_overdue(timezone.now()), "0 overdue requests flagged to OPS.")
        Request.objects.filter(pk=pr["id"]).update(approved_at=timezone.now() - timedelta(days=6))
        self.assertEqual(jobs.ops_overdue(timezone.now()), "1 overdue request flagged to OPS.")
        self.assertTrue(Notification.objects.filter(recipient=self.oscar, event="OPS_OVERDUE").exists())
        self.assertEqual(jobs.ops_overdue(timezone.now()), "0 overdue requests flagged to OPS.")


class DigestAndReportTests(PortalTestCase):
    def test_digest_goes_only_to_people_with_something_waiting(self):
        self.submitted_pr()
        mail.outbox.clear()
        self.assertEqual(jobs.daily_digest(timezone.now()), "1 summary email sent.")
        self.assertEqual(mail.outbox[-1].to, ["maria@example.com"])
        self.assertIn("Waiting for your approval (1)", mail.outbox[-1].body)

        self.as_user(self.maria).patch("/api/me/", {"preferences": {"email_digest": False}}, format="json")
        mail.outbox.clear()
        self.assertEqual(jobs.daily_digest(timezone.now()), "0 summary emails sent.")

    def test_monthly_report_covers_last_month(self):
        pr = self.submitted_pr()
        last_month = timezone.now().replace(day=1) - timedelta(days=3)
        Request.objects.filter(pk=pr["id"]).update(submitted_at=last_month)
        mail.outbox.clear()
        result = jobs.monthly_report(timezone.now())
        self.assertIn("1 request", result)
        report = mail.outbox[-1]
        self.assertEqual(sorted(report.to), ["admin@example.com", "fiona@example.com"])
        self.assertIn(pr["number"], report.attachments[0][1])


class DirectorySyncTests(PortalTestCase):
    def setUp(self):
        super().setUp()
        User.objects.filter(pk__in=[self.juan.pk, self.sofia.pk, self.oscar.pk, self.sam.pk, self.fiona.pk]).update(
            directory_username=None)
        for user in (self.juan, self.sofia, self.oscar, self.sam, self.fiona):
            User.objects.filter(pk=user.pk).update(directory_username=user.email.split("@")[0])

    def run_sync(self, missing=(), error=None):
        def find(username):
            if error:
                raise error
            return None if username in missing else mock.sentinel.entry
        with mock.patch("apps.users.directory.is_configured", return_value=True), \
             mock.patch("apps.users.directory.find", side_effect=find), \
             mock.patch("apps.users.directory.sync_user") as sync:
            return jobs.directory_sync(timezone.now()), sync

    def test_leavers_are_deactivated_and_others_refreshed(self):
        result, sync = self.run_sync(missing={"sofia"})
        self.assertEqual(result, "4 accounts refreshed, 1 deactivated.")
        self.assertEqual(sync.call_count, 4)
        self.assertFalse(User.objects.get(pk=self.sofia.pk).is_active)
        self.assertTrue(User.objects.get(pk=self.juan.pk).is_active)

    def test_nothing_changes_when_the_directory_is_unreachable_or_looks_wrong(self):
        from ldap3.core.exceptions import LDAPSocketOpenError

        with self.assertRaises(jobs.Skipped):
            self.run_sync(error=LDAPSocketOpenError("no route"))
        with self.assertRaises(RuntimeError):  # everyone "missing" means the directory is wrong, not that all left
            self.run_sync(missing={"juan", "sofia", "oscar", "sam", "fiona"})
        self.assertEqual(User.objects.filter(is_active=False).count(), 0)


class SchedulerTests(PortalTestCase):
    def test_each_job_keeps_its_own_timetable(self):
        hourly, daily, monthly = (runner.BY_KEY[k] for k in ("ops_overdue", "daily_digest", "monthly_report"))
        nine = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
        never = JobState(key="x")
        self.assertTrue(runner.is_due(hourly, never, nine))
        self.assertTrue(runner.is_due(daily, never, nine))
        self.assertFalse(runner.is_due(daily, never, nine.replace(hour=6)))  # digest waits for 8 AM
        ran = JobState(key="x", last_run_at=nine)
        self.assertFalse(runner.is_due(hourly, ran, nine + timedelta(minutes=30)))
        self.assertTrue(runner.is_due(hourly, ran, nine + timedelta(minutes=60)))
        self.assertFalse(runner.is_due(daily, ran, nine + timedelta(hours=5)))
        self.assertTrue(runner.is_due(daily, ran, nine + timedelta(days=1)))
        self.assertFalse(runner.is_due(monthly, ran, nine + timedelta(hours=5)))

    def test_outcomes_are_recorded_and_a_failure_does_not_stop_the_rest(self):
        boom = mock.Mock(side_effect=ValueError("broken"))
        fine = mock.Mock(return_value="done")
        test_jobs = [runner.Job("a_fails", "A", "", "hour", boom), runner.Job("b_works", "B", "", "hour", fine)]
        with mock.patch.object(runner, "JOBS", test_jobs):
            ran = runner.run_due()
        self.assertEqual([(job.key, state.last_status) for job, state in ran], [("a_fails", "failed"), ("b_works", "ok")])
        self.assertIn("broken", JobState.objects.get(key="a_fails").last_detail)
        JobState.objects.filter(key="b_works").update(enabled=False, last_run_at=None)
        with mock.patch.object(runner, "JOBS", test_jobs):
            self.assertEqual([job.key for job, _ in runner.run_due()], [])  # a ran within the hour, b is off

    def test_only_administrators_manage_automations(self):
        self.assertEqual(self.as_user(self.oscar).get("/api/automations/").status_code, 403)
        client = self.as_user(self.admin)
        listed = client.get("/api/automations/").data
        self.assertEqual(len(listed), len(runner.JOBS))
        off = client.patch("/api/automations/daily_digest/", {"enabled": False}, format="json")
        self.assertFalse(off.data["enabled"])
        ran = client.post("/api/automations/ops_overdue/run/")
        self.assertEqual(ran.data["last_status"], "ok")
        self.assertEqual(client.post("/api/automations/nope/run/").status_code, 404)


class OutOfOfficeTests(PortalTestCase):
    def cover(self, user, delegate, until=None):
        return self.as_user(user).put("/api/me/delegation/", {"delegate": str(delegate.id) if delegate else None,
                                                              "until": until}, format="json")

    def test_cover_can_see_and_approve_and_it_is_recorded(self):
        self.assertEqual(self.cover(self.maria, self.sam).status_code, 200)
        pr = self.submitted_pr()
        # Sam now has it in his list, can open it, and was notified.
        self.assertEqual([row["id"] for row in self.as_user(self.sam).get("/api/approvals/").data], [pr["id"]])
        self.assertEqual(self.as_user(self.sam).get(f"/api/requests/{pr['id']}/").status_code, 200)
        self.assertTrue(Notification.objects.filter(recipient=self.sam, event="APPROVAL_REQUIRED").exists())
        self.assertEqual(self.act(self.sam, pr["id"], "approve").status_code, 200)
        step = ApprovalStep.objects.get(instance__request_id=pr["id"], order=1)
        self.assertEqual((step.acted_by, step.on_behalf_of), (self.sam, self.maria))
        timeline = self.as_user(self.juan).get(f"/api/requests/{pr['id']}/timeline/").data["current"]
        self.assertIn("(for Maria Test)", timeline[1]["actor"])

    def test_cover_ends_and_the_original_approver_keeps_their_rights(self):
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual(self.cover(self.maria, self.sam, until=yesterday).status_code, 400)
        self.cover(self.maria, self.sam)
        pr = self.submitted_pr()
        User.objects.filter(pk=self.maria.pk).update(delegate_until=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self.as_user(self.sam).get("/api/approvals/").data, [])
        self.assertEqual(self.act(self.sam, pr["id"], "approve").status_code, 404)  # no longer visible to him
        self.assertEqual(self.act(self.maria, pr["id"], "approve").status_code, 200)

    def test_rules_for_choosing_a_cover(self):
        self.assertEqual(self.cover(self.maria, self.maria).status_code, 400)
        self.cover(self.maria, self.sam)
        self.assertEqual(self.cover(self.sam, self.maria).status_code, 400)  # no covering each other
        state = self.as_user(self.sam).get("/api/me/delegation/").data
        self.assertEqual(state["covering_for"], ["Maria Test"])
        self.assertIsNone(self.cover(self.maria, None).data["delegate"])
        # A requester's own request never becomes approvable by them through cover.
        self.cover(self.maria, self.juan)
        pr = self.submitted_pr()
        self.assertEqual(self.as_user(self.juan).get("/api/approvals/").data, [])
        self.assertEqual(self.act(self.juan, pr["id"], "approve").status_code, 403)

    def test_colleague_search(self):
        found = self.as_user(self.juan).get("/api/colleagues/?search=mar").data
        self.assertEqual([person["name"] for person in found], ["Maria Test"])
        self.assertEqual(self.as_user(self.juan).get("/api/colleagues/?search=m").data, [])
        self.assertEqual(self.as_user(self.juan).get("/api/colleagues/?search=juan").data, [])  # not yourself
