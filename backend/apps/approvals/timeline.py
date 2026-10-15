"""Builds the approval timeline shown on the request page and printed on the PDF."""

from apps.requests.models import Status
from apps.workflows.models import ApproverType

from .models import ActionType, InstanceStatus, StepStatus

_STEP_STATE = {
    StepStatus.WAITING: "upcoming",
    StepStatus.PENDING: "current",
    StepStatus.APPROVED: "done",
    StepStatus.REJECTED: "rejected",
    StepStatus.RETURNED: "returned",
    StepStatus.SKIPPED: "skipped",
    StepStatus.CANCELLED: "cancelled",
}
_STEP_DETAIL = {
    StepStatus.WAITING: "Waiting",
    StepStatus.PENDING: "Pending",
    StepStatus.APPROVED: "Approved",
    StepStatus.REJECTED: "Rejected",
    StepStatus.RETURNED: "Returned for revision",
    StepStatus.SKIPPED: "Skipped",
    StepStatus.CANCELLED: "Not reached",
}


def _node(key, label, state, detail="", actor="", position="", at=None, comments="", notes=None):
    return {"key": key, "label": label, "state": state, "detail": detail, "actor": actor,
            "actor_position": position, "at": at, "comments": comments, "notes": notes or []}


def _assignee(step, req):
    if step.approver_type == ApproverType.USER and step.user_id:
        return step.user.display_name
    if step.approver_type == ApproverType.ROLE and step.role_id:
        return step.role.name
    head = req.department.head
    return head.display_name if head else "Department Head"


def _decided_by(step):
    name = step.acted_by.display_name
    return f"{name} (for {step.on_behalf_of.display_name})" if step.on_behalf_of_id else name


def _step_nodes(steps, req):
    nodes = []
    for step in steps:
        decided = step.acted_by_id is not None
        clarifications = [
            {"actor": a.actor.display_name, "at": a.created_at, "text": a.comments}
            for a in step.actions.all() if a.action == ActionType.CLARIFY
        ]
        detail = _STEP_DETAIL[step.status]
        if step.status == StepStatus.PENDING and step.needs_clarification:
            detail = "Pending — clarification requested"
        nodes.append(_node(
            key=str(step.id), label=step.name, state=_STEP_STATE[step.status], detail=detail,
            actor=_decided_by(step) if decided else _assignee(step, req),
            position=step.acted_by_position if decided else "",
            at=step.acted_at or (step.activated_at if step.status == StepStatus.PENDING else None),
            comments=step.comments, notes=clarifications,
        ))
    return nodes


def _ops_nodes(req):
    """OPS receiving the request, then processing it."""
    received = req.ops_received_at
    # Requests completed before "processed" was recorded count as processed.
    processed = req.ops_processed_at or req.completed_at or (received and req.status == Status.FOR_FINANCE)
    assignee = req.ops_assignee.display_name if req.ops_assignee_id else "OPS"
    awaiting_receipt = req.status == Status.APPROVED
    working = req.status in (Status.OPS_RECEIVED, Status.PROCESSING)
    if processed:
        detail = "Processed"
    else:
        detail = {Status.PROCESSING: "In process", Status.OPS_RECEIVED: "Received, not yet started"}.get(req.status, "Waiting")
    return [
        _node("ops_received", "OPS", "done" if received else ("current" if awaiting_receipt else "upcoming"),
              detail="Received" if received else ("Awaiting receipt" if awaiting_receipt else "Waiting"),
              actor=assignee, at=received),
        _node("processing", "OPS Processing", "done" if processed else ("current" if working else "upcoming"),
              detail=detail, actor=assignee, at=req.ops_processed_at),
    ]


def build(req):
    """Return {"current": [...nodes], "previous": [{cycle, outcome, ended_at, nodes}]}.

    The current route reads in the order things happen: submitted, the approvals before
    OPS, OPS receiving and processing, the approvals after OPS, completed.
    """
    instances = list(
        req.approval_instances.prefetch_related(
            "steps__acted_by", "steps__user", "steps__role", "steps__actions__actor"
        )
    )
    if not instances:
        return {"current": [], "previous": []}

    latest = instances[-1]
    steps = list(latest.steps.all())
    alive = latest.status in (InstanceStatus.IN_PROGRESS, InstanceStatus.APPROVED)
    current = [_node("submitted", "Submitted", "done", detail="Submitted", actor=req.requester.display_name,
                     position=req.requester.position, at=latest.started_at)]
    current += _step_nodes([s for s in steps if not s.after_ops], req)
    if latest.requires_ops_processing and (alive or req.ops_received_at):
        current += _ops_nodes(req)
    current += _step_nodes([s for s in steps if s.after_ops], req)
    if alive:
        current.append(_node("completed", "Completed", "done" if req.completed_at else "upcoming",
                             detail="Completed" if req.completed_at else "Waiting", at=req.completed_at))

    previous = [
        {"cycle": inst.cycle, "outcome": inst.get_status_display(), "ended_at": inst.ended_at,
         "nodes": [_node("submitted", "Submitted", "done", detail="Submitted",
                         actor=req.requester.display_name, at=inst.started_at)] + _step_nodes(inst.steps.all(), req)}
        for inst in instances[:-1]
    ]
    return {"current": current, "previous": previous}

def approval_records(req):
    """Decided steps of the latest cycle, for the signature block of the printed form."""
    instance = req.approval_instances.prefetch_related("steps__acted_by").last()
    return list(instance.steps.all()) if instance else []
