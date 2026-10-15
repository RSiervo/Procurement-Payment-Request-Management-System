import logging
import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.template import Context, Engine, TemplateSyntaxError
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.models import SystemConfig
from apps.core.utils import format_date, format_datetime, format_money
from apps.users.preferences import wants_email

from .defaults import DEFAULT_TEMPLATES
from .models import EmailStatus, Event, Notification, NotificationTemplate

logger = logging.getLogger(__name__)

# Isolated engine: admin-authored templates cannot load or include other templates.
_engine = Engine(autoescape=False)


def render_text(source, context):
    return _engine.from_string(source).render(Context(context)).strip()


def validate_template(source):
    """Raise TemplateSyntaxError if the text is not a valid template."""
    _engine.from_string(source)


def request_url(req):
    return f"{settings.FRONTEND_URL}/requests/{req.id}"


def build_context(req, *, actor=None, comments="", config=None):
    config = config or SystemConfig.load()
    from apps.approvals.services import current_step  # local import: approvals depends on notifications

    step = current_step(req)
    return {
        "request_number": req.display_number,
        "request_type": req.request_type.name,
        "requester": req.requester.display_name,
        "department": req.department.name,
        "amount": format_money(req.total_amount, config.currency_symbol),
        "status": req.get_status_display(),
        "current_level": step.name if step else "",
        "date_submitted": format_datetime(req.submitted_at),
        "date_needed": format_date(req.date_needed),
        "total_items": str(req.lines.count()),
        "actor": actor.display_name if actor else "",
        "actor_position": actor.position if actor else "",
        "comments": comments or "",
        "action_date": format_datetime(timezone.now()),
        "company_name": config.company_name,
    }


def _details(context, req):
    rows = [
        ("Request number", context["request_number"]),
        ("Request type", context["request_type"]),
        ("Requested by", context["requester"]),
        ("Department", context["department"]),
        ("Amount", context["amount"]),
        ("Status", context["status"]),
        ("Current approval level", context["current_level"]),
        ("Date submitted", context["date_submitted"]),
        ("Date needed", context["date_needed"]),
        ("Total items", context["total_items"]),
    ]
    return [(label, value) for label, value in rows if value]


def notify(event, recipients, req, *, actor=None, comments=""):
    """Create in-app notifications and queue the matching emails.

    The actor is never notified about their own action. Emails go out only after
    the surrounding transaction commits, so a rollback sends nothing.
    """
    template = NotificationTemplate.objects.filter(event=event).first()
    if template and not template.is_active:
        return []
    subject_src, body_src = (template.subject, template.body) if template else DEFAULT_TEMPLATES[event]
    send_email = template.send_email if template else True

    context = build_context(req, actor=actor, comments=comments)
    created, seen = [], set()
    for user in recipients:
        if user is None or user.pk in seen or not user.is_active or (actor and user.pk == actor.pk):
            continue
        seen.add(user.pk)
        ctx = {**context, "recipient_name": user.first_name or user.display_name}
        try:
            title, message = render_text(subject_src, ctx), render_text(body_src, ctx)
        except TemplateSyntaxError:
            logger.exception("Notification template for %s is invalid; using the built-in wording.", event)
            default_subject, default_body = DEFAULT_TEMPLATES[event]
            title, message = render_text(default_subject, ctx), render_text(default_body, ctx)
        created.append(
            Notification(
                recipient=user,
                request=req,
                event=event,
                title=title[:200],
                message=message,
                email_status=(EmailStatus.PENDING if send_email and user.email and wants_email(user, event)
                              else EmailStatus.NOT_SENT),
            )
        )
    Notification.objects.bulk_create(created)

    pending = [n.pk for n in created if n.email_status == EmailStatus.PENDING]
    if pending:
        details, url = _details(context, req), request_url(req)
        transaction.on_commit(lambda: send_emails(pending, details, url))
    return created


_mail_down_until = 0.0


def send_emails(notification_ids, details, url):
    company = SystemConfig.load().company_name
    # One connection for the whole batch, so an unreachable mail server costs one wait, not one per person.
    # After a failed connection, do not try again for a few minutes: people must not wait on a dead mail server.
    global _mail_down_until
    connection = get_connection()
    try:
        if time.monotonic() < _mail_down_until:
            raise RuntimeError("The mail server could not be reached a moment ago; not retried yet.")
        try:
            connection.open()
        except Exception:
            _mail_down_until = time.monotonic() + 300
            raise
    except Exception as exc:
        logger.warning("Mail server unavailable, %s emails not sent: %s", len(notification_ids), exc)
        Notification.objects.filter(pk__in=notification_ids).update(
            email_status=EmailStatus.FAILED, email_error=str(exc)[:255]
        )
        return
    for note in Notification.objects.filter(pk__in=notification_ids).select_related("recipient"):
        # Approvers can start their decision from the email. The link only opens the
        # confirmation screen in the portal; nothing is decided until they confirm there.
        deciding = note.event in (Event.APPROVAL_REQUIRED, Event.APPROVAL_REMINDER)
        text = "\n".join(
            [f"Hello {note.recipient.first_name or note.recipient.display_name},", "", note.message, ""]
            + [f"{label}: {value}" for label, value in details]
            + ["", f"View request: {url}"]
            + ([f"Approve: {url}?action=approve", f"Return for revision: {url}?action=return"] if deciding else [])
        )
        html = render_to_string(
            "emails/notification.html",
            {"note": note, "details": details, "url": url, "company_name": company, "deciding": deciding},
        )
        try:
            email = EmailMultiAlternatives(note.title, text, to=[note.recipient.email], connection=connection)
            email.attach_alternative(html, "text/html")
            email.send()
        except Exception as exc:  # delivery problems must never break the user's action
            logger.warning("Email for notification %s failed: %s", note.pk, exc)
            Notification.objects.filter(pk=note.pk).update(
                email_status=EmailStatus.FAILED, email_error=str(exc)[:255]
            )
        else:
            Notification.objects.filter(pk=note.pk).update(
                email_status=EmailStatus.SENT, emailed_at=timezone.now(), email_error=""
            )
    connection.close()
