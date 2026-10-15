"""Read-side rules: which requests a user may see."""

from django.db.models import Count, OuterRef, Q, Subquery

from apps.users import delegation
from apps.users.models import Role
from apps.workflows.models import ApproverType

from .models import Request, RequestLine, Status


def visible_to(user):
    """Requests the user may open.

    - Anyone: requests they raised or prepared.
    - Administrators: everything.
    - OPS and Finance: everything that has been submitted.
    - Department heads: submitted requests of the departments they head.
    - Approvers: requests with a step assigned to them, past or present.
    """
    qs = Request.objects.all()
    if user.has_role(Role.ADMIN):
        return qs

    own = Q(requester=user) | Q(prepared_by=user)
    submitted = ~Q(status=Status.DRAFT)
    if user.has_role(Role.OPS, Role.FINANCE):
        return qs.filter(own | submitted)

    steps = "approval_instances__steps__"
    involved = (
        Q(**{steps + "acted_by": user})
        | Q(**{steps + "approver_type": ApproverType.USER, steps + "user": user})
        | Q(**{steps + "approver_type": ApproverType.ROLE, steps + "role__in": user.roles.all()})
    )
    # Someone covering for an approver sees what that approver would see.
    for person in delegation.active_delegators(user):
        involved |= (
            Q(**{steps + "approver_type": ApproverType.USER, steps + "user": person})
            | Q(**{steps + "approver_type": ApproverType.ROLE, steps + "role__in": person.roles.all()})
            | Q(department__head=person)
        )
    return qs.filter(own | (submitted & (Q(department__head=user) | involved))).distinct()


def with_summary(queryset):
    """Annotate each request with its first line's description and its number of lines."""
    lines = RequestLine.objects.filter(request=OuterRef("pk"))
    return queryset.annotate(
        first_line=Subquery(lines.order_by("position").values("description")[:1]),
        line_count=Subquery(lines.order_by().values("request").annotate(n=Count("pk")).values("n")[:1]),
    )


def base_queryset(user):
    return with_summary(visible_to(user)).select_related(
        "request_type", "requester", "prepared_by", "department", "ops_assignee", "source_request"
    )
