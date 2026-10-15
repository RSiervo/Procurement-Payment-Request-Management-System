"""Checks that protect against paying twice, overspending, and unknown payees.

Nothing here changes a request. The checks are shown to everyone handling the request
and recorded in the audit trail when it is submitted; only the budget check can stop a
submission, and only when the administrators have switched that on.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.models import SystemConfig
from apps.users.models import Role

from .models import OPS_STATUSES, Budget, FormKind, Request, RequestType, Status, Vendor

# Requests whose amount counts against a budget: everything submitted and not turned down.
COMMITTED_STATUSES = (Status.PENDING_APPROVAL, *OPS_STATUSES, Status.COMPLETED)
# A request with the same payee and amount within this many days is worth a second look.
SAME_AMOUNT_WINDOW_DAYS = 60
_PAYEE_KINDS = (FormKind.PAYMENT, FormKind.EXPENSE)


# --- Vendors -----------------------------------------------------------------

def match_vendor(payable_to):
    """The listed vendor a typed payee refers to, or None."""
    name = (payable_to or "").strip()
    return Vendor.objects.filter(is_active=True, name__iexact=name).first() if name else None


# --- Duplicates --------------------------------------------------------------

def possible_duplicates(req):
    """Other live payment requests that look like the same payment: [(request, reason)]."""
    payee = req.payable_to.strip()
    if req.request_type.form_kind not in _PAYEE_KINDS or not payee:
        return []
    same_payee = Q(payable_to__iexact=payee)
    if req.vendor_id:
        same_payee |= Q(vendor_id=req.vendor_id)
    others = (
        Request.objects.filter(same_payee, request_type__form_kind__in=_PAYEE_KINDS)
        .exclude(pk=req.pk).exclude(status__in=[Status.DRAFT, Status.REJECTED, Status.CANCELLED])
        .select_related("request_type")
    )
    found = {}
    invoice = req.invoice_number.strip()
    if invoice:
        for other in others.filter(invoice_number__iexact=invoice)[:5]:
            found[other.pk] = (other, f"Same payee and invoice number ({invoice})")
    if req.total_amount > 0:
        when = req.submitted_at or timezone.now()
        window = timedelta(days=SAME_AMOUNT_WINDOW_DAYS)
        nearby = others.filter(total_amount=req.total_amount, submitted_at__range=(when - window, when + window))
        for other in nearby.order_by("-submitted_at")[:5]:
            found.setdefault(other.pk, (other, f"Same payee and amount within {SAME_AMOUNT_WINDOW_DAYS} days"))
    return list(found.values())[:5]


# --- Budgets -----------------------------------------------------------------

def committed_amount(department_id, year, exclude=None):
    """Total of the department's submitted requests for the year.

    A payment linked to a Purchase Requisition pays for something that requisition
    already committed, so only the requisition is counted.
    """
    qs = Request.objects.filter(
        department_id=department_id, status__in=COMMITTED_STATUSES,
        submitted_at__year=year, source_request__isnull=True,
    )
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")


def budget_position(req):
    """Where this request leaves its department's budget, or None if no budget is set."""
    if req.status in (Status.REJECTED, Status.CANCELLED):
        return None
    year = timezone.localtime(req.submitted_at).year if req.submitted_at else timezone.localdate().year
    budget = Budget.objects.filter(department_id=req.department_id, year=year).first()
    if budget is None:
        return None
    this = req.total_amount if req.source_request_id is None else Decimal("0")
    used = committed_amount(req.department_id, year, exclude=req) + this
    return {
        "year": year, "department": req.department.name, "amount": budget.amount, "used": used,
        # A linked payment or a liquidation adds nothing, so it is never the one that goes over.
        "this_request": this, "remaining": budget.amount - used, "over": used > budget.amount and this > 0,
    }


def over_budget_message(position, symbol=""):
    return (
        f"This request takes {position['department']} over its {position['year']} budget: "
        f"{symbol}{position['used']:,.2f} committed against {symbol}{position['amount']:,.2f}."
    )


def blocks_submission(position):
    return bool(position and position["over"] and SystemConfig.load().block_over_budget)


def may_see_budget(user, req):
    """Budget figures are for the people who decide and account for spending, not every requester."""
    return user.has_role(Role.ADMIN, Role.FINANCE, Role.OPS) or req.department.head_id == user.pk


# --- Cash advances -----------------------------------------------------------

def live_liquidation(advance, exclude=None):
    """The liquidation filed against a cash advance, ignoring rejected and cancelled ones."""
    qs = advance.linked_requests.filter(request_type__code=RequestType.LIQ).exclude(
        status__in=[Status.REJECTED, Status.CANCELLED]
    )
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.select_related("request_type").first()


def open_advances(req):
    """The requester's other cash advances that were released and are not yet fully liquidated."""
    if req.request_type.code != RequestType.CA:
        return []
    liquidated = Request.objects.filter(
        request_type__code=RequestType.LIQ, status=Status.COMPLETED, source_request__isnull=False
    ).values("source_request_id")
    return list(
        Request.objects.filter(requester_id=req.requester_id, request_type__code=RequestType.CA, status=Status.COMPLETED)
        .exclude(pk=req.pk).exclude(pk__in=liquidated).order_by("completed_at")[:5]
    )


def advance_position(req):
    """For a liquidation: what was advanced, what was spent, and who owes whom. For an advance: its liquidation."""
    code = req.request_type.code
    if code == RequestType.LIQ and req.source_request_id:
        advanced, spent = req.source_request.total_amount, req.total_amount
        return {
            "role": "liquidation", "advance_id": req.source_request_id, "advance_number": req.source_request.number,
            "advance_amount": advanced, "spent": spent,
            "to_return": max(advanced - spent, Decimal("0")), "to_reimburse": max(spent - advanced, Decimal("0")),
        }
    if code == RequestType.CA:
        liquidation = live_liquidation(req)
        return {
            "role": "advance", "released": req.status == Status.COMPLETED,
            "liquidated": bool(liquidation and liquidation.status == Status.COMPLETED),
            "liquidation": {"id": liquidation.pk, "number": liquidation.display_number,
                            "status_display": liquidation.get_status_display(), "total_amount": liquidation.total_amount}
                           if liquidation else None,
        }
    return None


# --- Summary for the request screen ------------------------------------------

def summary(user, req, can_decide=False):
    """Everything the request screen shows under "Checks"."""
    from . import selectors

    duplicates = possible_duplicates(req)
    visible = set(selectors.visible_to(user).filter(pk__in=[other.pk for other, _ in duplicates])
                  .values_list("pk", flat=True)) if duplicates else set()
    position = budget_position(req)
    if position and position["this_request"] == 0 and position["remaining"] < 0:
        position = None  # the department is already over, but not because of this request
    if position and not (can_decide or may_see_budget(user, req)):
        # Others only learn that the budget is exceeded, not the figures.
        position = {"year": position["year"], "department": position["department"], "over": True} if position["over"] else None
    return {
        "duplicates": [
            {"id": other.pk if other.pk in visible else None, "number": other.display_number,
             "type_name": other.request_type.name, "status_display": other.get_status_display(),
             "total_amount": other.total_amount, "submitted_at": other.submitted_at, "reason": reason}
            for other, reason in duplicates
        ],
        "budget": position,
        "open_advances": [
            {"number": other.number, "total_amount": other.total_amount, "completed_at": other.completed_at}
            for other in open_advances(req)
        ],
        "unlisted_payee": bool(
            req.request_type.form_kind == FormKind.PAYMENT and req.payable_to.strip() and not req.vendor_id
            and Vendor.objects.filter(is_active=True).exists()
        ),
    }
