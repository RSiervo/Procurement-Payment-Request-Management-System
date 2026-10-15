from django.db.models import Q

from .models import Workflow


def resolve_workflow(request_type, department, amount):
    """Pick the workflow a request should follow, or None when nothing matches.

    Department-specific workflows beat generic ones; ties go to the higher priority.
    """
    candidates = (
        Workflow.objects.filter(request_type=request_type, is_active=True)
        .filter(Q(department=department) | Q(department__isnull=True))
        .filter(Q(min_amount__isnull=True) | Q(min_amount__lte=amount))
        .filter(Q(max_amount__isnull=True) | Q(max_amount__gte=amount))
        .prefetch_related("steps__role", "steps__user", "steps__level")
    )
    ranked = sorted(
        candidates,
        key=lambda w: (w.department_id is not None, w.priority, w.created_at),
        reverse=True,
    )
    return ranked[0] if ranked else None
