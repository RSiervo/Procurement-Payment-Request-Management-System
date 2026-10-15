"""Decides which automations are due and runs them.

`manage.py run_automations` is called every few minutes by the operating system's
scheduler. Each job keeps its own record of when it last ran, so the caller does not
need to know any job's timetable.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from django.utils import timezone

from . import jobs
from .models import JobState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    key: str
    name: str
    description: str
    every: str            # "hour", "day" or "month"
    run: Callable
    hour: int = 0         # for daily and monthly jobs: not before this hour, local time

    @property
    def schedule(self):
        if self.every == "hour":
            return "Every hour"
        when = f"{self.hour % 12 or 12}:00 {'AM' if self.hour < 12 else 'PM'}"
        return f"Daily at {when}" if self.every == "day" else f"1st of each month, {when}"


JOBS = [
    Job("approval_reminders", "Approval reminders",
        "Reminds an approver when a request has waited for them longer than the reminder days, and again each time that many days pass.",
        "hour", jobs.approval_reminders),
    Job("approval_escalation", "Approval escalation",
        "Tells the administrators, once, when a request has waited at one step longer than the escalation days.",
        "hour", jobs.approval_escalation),
    Job("ops_overdue", "OPS overdue alerts",
        "Alerts OPS, once per request, when an approved request has not been processed within the OPS target days.",
        "hour", jobs.ops_overdue),
    Job("daily_digest", "Daily summary email",
        "Emails each person a morning list of what is waiting for their approval and what was returned to them. People can switch it off in Settings.",
        "day", jobs.daily_digest, hour=8),
    Job("directory_sync", "Active Directory sync",
        "Refreshes names, departments and roles from Active Directory, and deactivates accounts of people who have left.",
        "day", jobs.directory_sync, hour=1),
    Job("backup", "Backup",
        "Saves the database and all uploaded files. The last 14 backups are kept.",
        "day", jobs.backup, hour=0),
    Job("monthly_report", "Monthly report",
        "Emails administrators and Finance a summary and spreadsheet of the previous month's requests.",
        "month", jobs.monthly_report, hour=7),
]
BY_KEY = {job.key: job for job in JOBS}


def is_due(job, state, now):
    last = timezone.localtime(state.last_run_at) if state.last_run_at else None
    local = timezone.localtime(now)
    if job.every == "hour":
        return last is None or now - state.last_run_at >= timedelta(minutes=55)
    if local.hour < job.hour:
        return False
    if job.every == "day":
        return last is None or last.date() < local.date()
    return last is None or (last.year, last.month) != (local.year, local.month)


def run_job(job, now=None):
    """Run one job now and record the outcome. Returns its JobState."""
    now = now or timezone.now()
    state, _ = JobState.objects.get_or_create(key=job.key)
    # Two schedulers (or a "Run now" click) must not run the same job at once.
    claimed = JobState.objects.filter(key=job.key).filter(
        running_since__isnull=True) | JobState.objects.filter(key=job.key, running_since__lt=now - timedelta(minutes=30))
    if not claimed.update(running_since=now):
        return state
    try:
        status, detail = JobState.OK, job.run(now)
    except jobs.Skipped as skipped:
        status, detail = JobState.SKIPPED, str(skipped)
    except Exception as exc:  # a failing job must never stop the others
        logger.exception("Automation %s failed", job.key)
        status, detail = JobState.FAILED, f"{exc.__class__.__name__}: {exc}"[:500]
    JobState.objects.filter(key=job.key).update(
        running_since=None, last_run_at=now, last_status=status, last_detail=(detail or "")[:500]
    )
    state.refresh_from_db()
    return state


def run_due(now=None, only=None, force=False):
    """Run every enabled job that is due. Returns [(job, state)] for the ones that ran."""
    now = now or timezone.now()
    ran = []
    for job in JOBS:
        if only and job.key != only:
            continue
        state, _ = JobState.objects.get_or_create(key=job.key)
        if not force and not (state.enabled and is_due(job, state, now)):
            continue
        ran.append((job, run_job(job, now)))
    return ran
