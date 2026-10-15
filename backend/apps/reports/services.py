"""Aggregations behind the dashboard and the reports page."""

from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.approvals import services as approvals
from apps.approvals.models import ActionType, ApprovalAction
from apps.requests import controls, selectors
from apps.requests import services as request_services
from apps.requests.models import OPS_STATUSES, Budget, Request, RequestType, Status
from apps.users.models import Role, User
from apps.workflows.models import Workflow

REPORT_ROLES = (Role.ADMIN, Role.OPS, Role.FINANCE)


# --- Dashboard ---------------------------------------------------------------

def _count(qs, **filters):
    return qs.filter(**filters).count()


def dashboard(user, days=7):
    mine = Request.objects.filter(Q(requester=user) | Q(prepared_by=user))
    today = timezone.localdate()
    data = {
        "requester": {
            "total": mine.count(),
            "drafts": _count(mine, status=Status.DRAFT),
            "pending": _count(mine, status=Status.PENDING_APPROVAL),
            "approved": _count(mine, status__in=OPS_STATUSES),
            "returned": _count(mine, status=Status.RETURNED),
            "rejected": _count(mine, status=Status.REJECTED),
            "completed": _count(mine, status=Status.COMPLETED),
        },
        "approver": None,
        "ops": None,
        "admin": None,
    }

    my_actions = ApprovalAction.objects.filter(actor=user)
    pending = approvals.pending_steps_for(user).count()
    is_approver = user.has_role(Role.APPROVER, Role.DEPARTMENT_HEAD, Role.FINANCE) or user.headed_departments.exists()
    if is_approver or pending or my_actions.exists():
        data["approver"] = {
            "pending": pending,
            "approved_today": my_actions.filter(action=ActionType.APPROVE, created_at__date=today).count(),
            "returned": my_actions.filter(action=ActionType.RETURN).count(),
            "rejected": my_actions.filter(action=ActionType.REJECT).count(),
        }

    if user.has_role(Role.OPS):  # Finance only approves; the OPS queues are not theirs
        submitted = Request.objects.exclude(status=Status.DRAFT)
        data["ops"] = {
            "new": _count(submitted, status=Status.APPROVED),
            "pending_processing": _count(submitted, status=Status.OPS_RECEIVED),
            "in_process": _count(submitted, status=Status.PROCESSING),
            "waiting_finance": _count(submitted, status__in=[Status.INTERNAL_APPROVAL, Status.FOR_FINANCE]),
            "completed": _count(submitted, status=Status.COMPLETED),
            "overdue": submitted.filter(request_services.overdue_q()).count(),
        }

    if user.has_role(Role.ADMIN):
        submitted = Request.objects.exclude(status=Status.DRAFT)
        data["admin"] = {
            "total": submitted.count(),
            "pending_approval": _count(submitted, status=Status.PENDING_APPROVAL),
            "ops_processing": _count(submitted, status__in=OPS_STATUSES),
            "completed": _count(submitted, status=Status.COMPLETED),
            "active_users": User.objects.filter(is_active=True).count(),
            "active_workflows": Workflow.objects.filter(is_active=True).count(),
        }

    visible = selectors.visible_to(user).exclude(status=Status.DRAFT)
    data["activity"] = monthly_activity(visible)
    data["overview"] = daily_by_type(visible, days)
    data["by_type"] = type_distribution(visible)
    data["insights"] = insights(mine)
    return data


def _month_pair(qs, field):
    """How many records fall in this calendar month and in the previous one, by a date field."""
    this_month = timezone.localdate().replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    return {
        "current": qs.filter(**{f"{field}__date__gte": this_month}).count(),
        "previous": qs.filter(**{f"{field}__date__gte": last_month, f"{field}__date__lt": this_month}).count(),
    }


def insights(mine):
    """The line under each headline number on the requester dashboard."""
    stale_cutoff = timezone.now() - timedelta(days=3)
    return {
        "created": _month_pair(mine, "created_at"),
        "completed": _month_pair(mine, "completed_at"),
        "pending_over_3_days": mine.filter(status=Status.PENDING_APPROVAL, submitted_at__lt=stale_cutoff).count(),
        "processing_overdue": mine.filter(status__in=OPS_STATUSES).filter(request_services.overdue_q()).count(),
    }


def daily_by_type(qs, days=7):
    """Requests submitted per day for the last N days, split by request type."""
    today = timezone.localdate()
    dates = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    counts = {}
    rows = (
        qs.filter(submitted_at__date__gte=dates[0])
        .annotate(day=TruncDate("submitted_at"))
        .values("day", "request_type__code")
        .annotate(count=Count("id", distinct=True))
        .order_by()
    )
    for row in rows:
        counts[(row["day"], row["request_type__code"])] = row["count"]
    codes = list(RequestType.objects.filter(is_active=True).values_list("code", flat=True))
    return [
        {"date": day.isoformat(), "label": f"{day:%b} {day.day}",
         "counts": {code: counts.get((day, code), 0) for code in codes}}
        for day in dates
    ]


def type_distribution(qs):
    """How many submitted requests of each type the user can see."""
    counts = dict(
        qs.values_list("request_type__code").annotate(count=Count("id", distinct=True)).order_by()
    )
    return [
        {"code": rtype.code, "name": rtype.name, "count": counts.get(rtype.code, 0)}
        for rtype in RequestType.objects.filter(is_active=True)
    ]


def monthly_activity(qs, months=6):
    """Submitted-request counts for the last N calendar months, oldest first, gaps filled with zero."""
    first = timezone.localdate().replace(day=1)
    starts = []
    for _ in range(months):
        starts.append(first)
        first = (first - timedelta(days=1)).replace(day=1)
    starts.reverse()
    counts = {
        row["month"].date(): row["count"]
        for row in qs.filter(submitted_at__date__gte=starts[0])
        .annotate(month=TruncMonth("submitted_at")).values("month").annotate(count=Count("id", distinct=True)).order_by("month")
    }
    return [{"month": start.isoformat(), "label": f"{start:%b}", "count": counts.get(start, 0)} for start in starts]


# --- Reports -----------------------------------------------------------------

def report_queryset(user, filters):
    """Submitted requests the user may report on, narrowed by the common report filters."""
    qs = Request.objects.exclude(status=Status.DRAFT)
    if not user.has_role(*REPORT_ROLES):
        headed = user.headed_departments.all()
        if not headed.exists():
            raise PermissionDenied("You do not have access to reports.")
        qs = qs.filter(department__in=headed)
    if filters.get("date_from"):
        qs = qs.filter(submitted_at__date__gte=filters["date_from"])
    if filters.get("date_to"):
        qs = qs.filter(submitted_at__date__lte=filters["date_to"])
    if filters.get("type"):
        qs = qs.filter(request_type__code=filters["type"])
    if filters.get("department"):
        qs = qs.filter(department_id=filters["department"])
    if filters.get("status"):
        qs = qs.filter(status=filters["status"])
    return qs


def _grouped(qs, field, key=None):
    """Counts and amounts per value of a field. `key` adds the value the screen filters by."""
    names = {"label": F(field), **({"key": F(key)} if key else {})}
    rows = qs.values(**names).annotate(count=Count("id"), amount=Sum("total_amount")).order_by("-count")
    return [{**({"key": str(r["key"])} if key else {}), "label": r["label"], "count": r["count"], "amount": r["amount"] or 0}
            for r in rows]


def by_payee(qs, limit=15):
    """Who the money goes to: payment requests that were not turned down, largest total first."""
    rows = (
        qs.exclude(payable_to="").exclude(status__in=[Status.REJECTED, Status.CANCELLED, Status.RETURNED])
        .values(label=F("payable_to"), listed=F("vendor_id"))
        .annotate(count=Count("id"), amount=Sum("total_amount")).order_by("-amount")[:limit]
    )
    return [{"label": r["label"], "count": r["count"], "amount": r["amount"] or 0, "listed": r["listed"] is not None}
            for r in rows]


def _days(delta):
    return round(delta.total_seconds() / 86400, 1) if delta is not None else None


def summary(qs):
    totals = qs.aggregate(
        requests=Count("id"),
        amount=Sum("total_amount"),
        completed=Count("id", filter=Q(status=Status.COMPLETED)),
        rejected=Count("id", filter=Q(status=Status.REJECTED)),
        pending_approval=Count("id", filter=Q(status=Status.PENDING_APPROVAL)),
        reimbursement_total=Sum(
            "total_amount",
            filter=Q(request_type__code=RequestType.REIM, status__in=[*OPS_STATUSES, Status.COMPLETED]),
        ),
    )
    status_labels = dict(Status.choices)
    by_status = [{**row, "label": status_labels.get(row["label"], row["label"]), "status": row["label"]}
                 for row in _grouped(qs, "status")]
    monthly = [
        {"label": f"{r['month']:%b %Y}", "count": r["count"], "amount": r["amount"] or 0}
        for r in qs.exclude(submitted_at__isnull=True).annotate(month=TruncMonth("submitted_at"))
        .values("month").annotate(count=Count("id"), amount=Sum("total_amount")).order_by("month")
    ]

    def duration(end):
        return ExpressionWrapper(F(end) - F("submitted_at"), output_field=DurationField())

    processing = [
        {"label": r["request_type__name"], "completed": r["completed"],
         "avg_days_to_approve": _days(r["to_approve"]), "avg_days_to_complete": _days(r["to_complete"])}
        for r in qs.values("request_type__name").annotate(
            completed=Count("id", filter=Q(status=Status.COMPLETED)),
            to_approve=Avg(duration("approved_at"), filter=Q(approved_at__isnull=False)),
            to_complete=Avg(duration("completed_at"), filter=Q(status=Status.COMPLETED)),
        ).order_by("request_type__name")
    ]
    return {
        "totals": {k: (v or 0) for k, v in totals.items()},
        "by_department": _grouped(qs, "department__name", key="department_id"),
        "by_type": _grouped(qs, "request_type__name", key="request_type__code"),
        "by_payee": by_payee(qs),
        "by_status": by_status,
        "monthly": monthly,
        "processing_time": processing,
    }


# --- Analytics ---------------------------------------------------------------

def _trend(qs, start, end):
    """Requests and amount over time, by day for short periods and by month otherwise, gaps filled."""
    daily = (end - start).days <= 62
    trunc = TruncDate("submitted_at") if daily else TruncMonth("submitted_at")
    found = {}
    for row in (qs.exclude(submitted_at__isnull=True).annotate(bucket=trunc).values("bucket")
                .annotate(count=Count("id"), amount=Sum("total_amount")).order_by("bucket")):
        bucket = row["bucket"] if daily else timezone.localtime(row["bucket"]).date()
        found[bucket] = row
    points, cursor = [], start if daily else start.replace(day=1)
    while cursor <= end and len(points) < 400:
        row = found.get(cursor)
        points.append({
            "date": cursor.isoformat(),
            "label": f"{cursor:%b} {cursor.day}" if daily else f"{cursor:%b %Y}",
            "count": row["count"] if row else 0, "amount": (row["amount"] or 0) if row else 0,
        })
        cursor = cursor + timedelta(days=1) if daily else (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {"unit": "day" if daily else "month", "points": points}


def _headline(qs):
    totals = qs.aggregate(requests=Count("id"), amount=Sum("total_amount"),
                          completed=Count("id", filter=Q(status=Status.COMPLETED)))
    return {key: value or 0 for key, value in totals.items()}


def analytics(user, filters):
    """Everything the Analytics page shows for one set of filters."""
    qs = report_queryset(user, filters)
    data = summary(qs)
    today = timezone.localdate()
    first = qs.exclude(submitted_at__isnull=True).order_by("submitted_at").values_list("submitted_at", flat=True).first()
    start = filters.get("date_from") or (timezone.localtime(first).date() if first else today)
    end = filters.get("date_to") or today
    data["trend"] = _trend(qs, min(start, end), end)

    # The period of the same length just before this one, for "up / down" on the headline numbers.
    data["previous"] = None
    if filters.get("date_from") and filters.get("date_to"):
        length = (end - start).days + 1
        before = {**filters, "date_from": start - timedelta(days=length), "date_to": start - timedelta(days=1)}
        data["previous"] = _headline(report_queryset(user, before))

    data["funnel"] = qs.aggregate(
        submitted=Count("id"),
        approved=Count("id", filter=Q(approved_at__isnull=False)),
        processed=Count("id", filter=Q(ops_processed_at__isnull=False) | Q(status=Status.COMPLETED)),
        completed=Count("id", filter=Q(status=Status.COMPLETED)),
    )

    data["budgets"] = []
    if user.has_role(Role.ADMIN, Role.FINANCE):
        budgets = Budget.objects.filter(year=end.year).select_related("department")
        if filters.get("department"):
            budgets = budgets.filter(department_id=filters["department"])
        data["budgets"] = [
            {"key": str(b.department_id), "label": b.department.name, "year": b.year, "amount": b.amount,
             "used": controls.committed_amount(b.department_id, b.year)}
            for b in budgets
        ]
    return data


# --- Export tables -----------------------------------------------------------

def _request_rows(qs):
    qs = qs.select_related("request_type", "requester", "department").order_by("-submitted_at")
    return [
        [r.number, r.request_type.name, r.requester.display_name, r.department.name, r.total_amount,
         r.get_status_display(), r.current_handler,
         timezone.localtime(r.submitted_at).date() if r.submitted_at else "",
         timezone.localtime(r.completed_at).date() if r.completed_at else ""]
        for r in qs[:5000]
    ]


_REQUEST_HEADERS = ["Request #", "Type", "Requester", "Department", "Amount", "Status",
                    "Currently with", "Submitted", "Completed"]
_COUNT_HEADERS = ["Requests", "Total amount"]


def _count_table(title, first_header, rows):
    return title, [first_header, *_COUNT_HEADERS], [[r["label"], r["count"], r["amount"]] for r in rows]


def export_table(report, qs):
    """Return (title, headers, rows) for a named report, or None if the name is unknown."""
    request_reports = {
        "all_requests": ("All Requests", qs),
        "pending_approvals": ("Pending Approvals", qs.filter(status=Status.PENDING_APPROVAL)),
        "completed": ("Completed Requests", qs.filter(status=Status.COMPLETED)),
        "rejected": ("Rejected Requests", qs.filter(status=Status.REJECTED)),
        "reimbursements": ("Reimbursements", qs.filter(request_type__code=RequestType.REIM)),
    }
    if report in request_reports:
        title, subset = request_reports[report]
        return title, _REQUEST_HEADERS, _request_rows(subset)

    data = summary(qs)
    if report == "by_department":
        return _count_table("Requests by Department", "Department", data["by_department"])
    if report == "by_type":
        return _count_table("Requests by Type", "Type", data["by_type"])
    if report == "by_payee":
        return _count_table("Spend by Payee", "Payee", data["by_payee"])
    if report == "by_status":
        return _count_table("Requests by Status", "Status", data["by_status"])
    if report == "monthly":
        return _count_table("Monthly Requests", "Month", data["monthly"])
    if report == "processing_time":
        return ("Processing Time", ["Type", "Completed", "Avg. days to approve", "Avg. days to complete"],
                [[r["label"], r["completed"], r["avg_days_to_approve"] or "", r["avg_days_to_complete"] or ""]
                 for r in data["processing_time"]])
    return None
