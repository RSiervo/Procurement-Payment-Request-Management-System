"""The work each automation does.

Every job takes the current time and returns a one-line result for the administrators'
screen. A job raises `Skipped` when there was nothing it could do (for example, the
directory cannot be reached); any other exception is recorded as a failure.
"""

import csv
import io
import os
import shutil
import subprocess
from datetime import timedelta
from glob import glob
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.db.models import Q
from django.utils import timezone

from apps.approvals import services as approvals
from apps.approvals.models import ApprovalStep, InstanceStatus, StepStatus
from apps.audit import services as audit
from apps.core.models import SystemConfig
from apps.core.utils import format_date, format_money
from apps.notifications import services as notifications
from apps.notifications.models import Event
from apps.requests.models import Request, Status
from apps.users import directory, preferences
from apps.users.models import Role, User

BACKUPS_KEPT = 14


class Skipped(Exception):
    """The job could not run this time; nothing was changed."""


def _plural(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


# --- Approvals that are taking too long ---------------------------------------

def _waiting_steps(cutoff):
    return ApprovalStep.objects.filter(
        status=StepStatus.PENDING, instance__status=InstanceStatus.IN_PROGRESS, activated_at__lte=cutoff
    ).select_related("instance__request__request_type", "instance__request__requester",
                     "instance__request__department__head", "role", "user")


def approval_reminders(now):
    """Remind approvers about steps that have waited longer than the configured days."""
    days = SystemConfig.load().reminder_after_days
    if not days:
        raise Skipped("Reminders are switched off (reminder days is 0).")
    cutoff = now - timedelta(days=days)
    sent = 0
    for step in _waiting_steps(cutoff).filter(Q(reminded_at__isnull=True) | Q(reminded_at__lte=cutoff)):
        request = step.instance.request
        notifications.notify(Event.APPROVAL_REMINDER, approvals.eligible_approvers(step, request), request)
        step.reminded_at = now
        step.save(update_fields=["reminded_at"])
        sent += 1
    return f"{_plural(sent, 'reminder')} sent."


def approval_escalation(now):
    """Tell the administrators, once, about steps that have waited far too long."""
    days = SystemConfig.load().escalate_after_days
    if not days:
        raise Skipped("Escalation is switched off (escalation days is 0).")
    admins = list(User.objects.filter(roles__code=Role.ADMIN, is_active=True).distinct())
    escalated = 0
    for step in _waiting_steps(now - timedelta(days=days)).filter(escalated_at__isnull=True):
        request = step.instance.request
        approver_ids = {user.pk for user in approvals.eligible_approvers(step, request)}
        notifications.notify(Event.APPROVAL_ESCALATED, [a for a in admins if a.pk not in approver_ids], request)
        step.escalated_at = now
        step.save(update_fields=["escalated_at"])
        audit.log(None, "APPROVAL_ESCALATED", f"{request.display_number} escalated: waiting at {step.name} for over {days} days",
                  request=request)
        escalated += 1
    return f"{_plural(escalated, 'request')} escalated to the administrators."


def ops_overdue(now):
    """Alert OPS, once per request, when processing has passed the target number of days."""
    days = SystemConfig.load().ops_sla_days
    overdue = Request.objects.filter(
        status__in=[Status.APPROVED, Status.OPS_RECEIVED, Status.PROCESSING],
        approved_at__lte=now - timedelta(days=days), ops_alerted_at__isnull=True,
    ).select_related("request_type", "requester", "department", "ops_assignee")
    ops_users = list(User.objects.filter(roles__code=Role.OPS, is_active=True).distinct())
    alerted = 0
    for request in overdue:
        notifications.notify(Event.OPS_OVERDUE, ops_users, request)
        request.ops_alerted_at = now
        request.save(update_fields=["ops_alerted_at"])
        alerted += 1
    return f"{_plural(alerted, 'overdue request')} flagged to OPS."


# --- Daily digest -------------------------------------------------------------

def daily_digest(now):
    """One morning email per person listing what is waiting for them."""
    config = SystemConfig.load()
    sent = 0
    for user in User.objects.filter(is_active=True).exclude(email=""):
        if not preferences.for_user(user)["email_digest"]:
            continue
        waiting = list(
            Request.objects.filter(pk__in=approvals.pending_steps_for(user).values("instance__request"))
            .select_related("request_type", "requester").order_by("submitted_at")[:20]
        )
        returned = list(
            Request.objects.filter(requester=user, status=Status.RETURNED).select_related("request_type")[:20]
        )
        if not waiting and not returned:
            continue
        lines = [f"Hello {user.first_name or user.display_name},", ""]
        if waiting:
            lines.append(f"Waiting for your approval ({len(waiting)}):")
            lines += [f"  - {r.display_number}  {r.request_type.name}  {format_money(r.total_amount, config.currency_symbol)}"
                      f"  from {r.requester.display_name}" for r in waiting]
            lines.append("")
        if returned:
            lines.append(f"Returned to you for revision ({len(returned)}):")
            lines += [f"  - {r.display_number}  {r.request_type.name}" for r in returned]
            lines.append("")
        lines += [f"Open the portal: {settings.FRONTEND_URL}/approvals" if waiting else f"Open the portal: {settings.FRONTEND_URL}/requests",
                  "", "You can switch this daily summary off under Settings in the portal."]
        subject = f"Your daily summary: {_plural(len(waiting) + len(returned), 'item')} waiting"
        try:
            send_mail(subject, "\n".join(lines), None, [user.email])
            sent += 1
        except Exception:  # one bad mailbox must not stop everyone else's summary
            continue
    return f"{_plural(sent, 'summary email')} sent."


# --- Active Directory ---------------------------------------------------------

def directory_sync(now):
    """Refresh names, departments and roles from the directory; deactivate people who have left.

    Nothing is changed unless every lookup succeeded, and the job stops without touching
    any account if an unusual share of people appear to be missing - that is far more
    likely to be a directory or configuration problem than a real mass departure.
    """
    from ldap3.core.exceptions import LDAPException

    if not directory.is_configured():
        raise Skipped("Active Directory is not configured.")
    users = list(User.objects.filter(is_active=True).exclude(directory_username__isnull=True).exclude(directory_username=""))
    if not users:
        raise Skipped("No Active Directory accounts have signed in yet.")
    found, missing = [], []
    try:
        for user in users:
            entry = directory.find(user.directory_username)
            (found if entry else missing).append((user, entry))
    except LDAPException as exc:
        raise Skipped(f"The directory could not be reached ({exc.__class__.__name__}); no accounts were changed.") from None
    if len(missing) > max(3, len(users) // 4):
        raise RuntimeError(f"{len(missing)} of {len(users)} accounts were not found in the directory. "
                           "That looks like a directory problem, so no accounts were changed.")
    for _, entry in found:
        directory.sync_user(entry)
    for user, _ in missing:
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])
        audit.log(None, "USER_DEACTIVATED", f"{user.display_name} was deactivated: no longer active in Active Directory")
    return f"{_plural(len(found), 'account')} refreshed, {len(missing)} deactivated."


# --- Backups ------------------------------------------------------------------

def _pg_dump():
    candidates = [os.environ.get("PG_DUMP_PATH", ""), shutil.which("pg_dump") or ""]
    candidates += sorted(glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"), reverse=True)
    for path in candidates:
        if path and os.path.exists(path):
            return path
    raise Skipped("pg_dump was not found. Set PG_DUMP_PATH in the backend .env file.")


def backup_folder():
    return Path(settings.BASE_DIR).parent / ".local" / "backups" / "auto"


def backup(now):
    """Save the database and the uploaded files (attachments, signatures, logo); keep the last 14 of each."""
    folder = backup_folder()
    folder.mkdir(parents=True, exist_ok=True)
    database = settings.DATABASES["default"]
    stamp = timezone.localtime(now).strftime("%Y%m%d-%H%M")
    target = folder / f"database-{stamp}.dump"
    command = [_pg_dump(), "-h", database.get("HOST") or "127.0.0.1", "-p", str(database.get("PORT") or 5432),
               "-U", database["USER"], "-d", database["NAME"], "-Fc", "-f", str(target)]
    result = subprocess.run(command, env={**os.environ, "PGPASSWORD": database.get("PASSWORD") or ""},
                            capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"The database backup failed: {result.stderr.strip()[:200]}")
    saved = [target.name]
    if Path(settings.MEDIA_ROOT).exists():
        shutil.make_archive(str(folder / f"files-{stamp}"), "zip", settings.MEDIA_ROOT)
        saved.append(f"files-{stamp}.zip")
    for pattern in ("database-*.dump", "files-*.zip"):
        for old in sorted(folder.glob(pattern), reverse=True)[BACKUPS_KEPT:]:
            old.unlink(missing_ok=True)
    size = sum((folder / name).stat().st_size for name in saved) / (1024 * 1024)
    return f"Saved {' and '.join(saved)} ({size:.1f} MB) in .local/backups/auto."


# --- Monthly report -----------------------------------------------------------

def monthly_report(now):
    """Email last month's requests, with a short summary, to administrators and Finance."""
    first_of_this_month = timezone.localtime(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = (first_of_this_month - timedelta(days=1)).replace(day=1)
    requests = list(
        Request.objects.filter(submitted_at__gte=start, submitted_at__lt=first_of_this_month)
        .select_related("request_type", "requester", "department").order_by("submitted_at")
    )
    recipients = sorted(set(
        User.objects.filter(roles__code__in=[Role.ADMIN, Role.FINANCE], is_active=True).exclude(email="")
        .values_list("email", flat=True)
    ))
    if not recipients:
        raise Skipped("No administrator or Finance user has an email address.")

    config = SystemConfig.load()
    sheet = io.StringIO()
    writer = csv.writer(sheet)
    writer.writerow(["Request #", "Type", "Requester", "Department", "Amount", "Status", "Submitted", "Completed"])
    for r in requests:
        writer.writerow([r.display_number, r.request_type.name, r.requester.display_name, r.department.name,
                         f"{r.total_amount:.2f}", r.get_status_display(),
                         format_date(timezone.localtime(r.submitted_at).date()),
                         format_date(timezone.localtime(r.completed_at).date()) if r.completed_at else ""])
    total = sum(r.total_amount for r in requests)
    by_status = {}
    for r in requests:
        by_status[r.get_status_display()] = by_status.get(r.get_status_display(), 0) + 1
    month = f"{start:%B %Y}"
    body = "\n".join([
        f"Requests submitted in {month}: {len(requests)}",
        f"Total amount: {format_money(total, config.currency_symbol)}",
        "",
        *[f"  {status}: {count}" for status, count in sorted(by_status.items())],
        "",
        "The full list is attached." if requests else "No requests were submitted in the month.",
    ])
    email = EmailMessage(f"{config.company_name}: requests report for {month}", body, None, recipients)
    if requests:
        email.attach(f"requests-{start:%Y-%m}.csv", "\ufeff" + sheet.getvalue(), "text/csv")
    email.send()
    return f"Report for {month} ({_plural(len(requests), 'request')}) sent to {_plural(len(recipients), 'person')}."
