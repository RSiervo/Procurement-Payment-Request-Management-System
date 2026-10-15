"""The approval engine.

All routing decisions live here: who may act on a step, what happens after each
decision, and how the request's status follows. Views and serializers only call in.
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import services as audit
from apps.core.models import SystemConfig
from apps.notifications import services as notifications
from apps.notifications.models import Event
from apps.requests.models import AWAITING_APPROVAL, Status
from apps.users import delegation, signatures
from apps.users.models import Role, User
from apps.workflows.models import ApproverType

from .models import ActionType, ApprovalAction, ApprovalInstance, ApprovalStep, InstanceStatus, StepStatus


def current_step(req):
    return (
        ApprovalStep.objects.filter(
            instance__request=req, instance__status=InstanceStatus.IN_PROGRESS, status=StepStatus.PENDING
        )
        .select_related("instance", "role", "user")
        .first()
    )


def direct_approvers(step, req):
    """Active users the step itself names: the person, the role's holders, or the department head."""
    if step.approver_type == ApproverType.USER:
        users = User.objects.filter(pk=step.user_id)
    elif step.approver_type == ApproverType.ROLE:
        users = User.objects.filter(roles=step.role_id)
    else:
        users = User.objects.filter(pk=req.department.head_id)
    users = users.filter(is_active=True)
    if not SystemConfig.load().allow_self_approval:
        users = users.exclude(pk=req.requester_id)
    return list(users.distinct())


def eligible_approvers(step, req):
    """Everyone who may decide this step: the named approvers plus whoever is covering for them."""
    approvers = direct_approvers(step, req)
    seen = {user.pk for user in approvers}
    self_approval = SystemConfig.load().allow_self_approval
    for user in list(approvers):
        cover = delegation.active_delegate(user)
        if cover and cover.pk not in seen and (self_approval or cover.pk != req.requester_id):
            approvers.append(cover)
            seen.add(cover.pk)
    return approvers


def can_act(user, step, req):
    return any(u.pk == user.pk for u in eligible_approvers(step, req))


def pending_steps_for(user):
    """Steps currently waiting on this user, across all requests."""
    mine = Q()
    # Steps addressed to this person, and to anyone they are covering for.
    for person in [user, *delegation.active_delegators(user)]:
        mine |= (
            Q(approver_type=ApproverType.USER, user=person)
            | Q(approver_type=ApproverType.ROLE, role__in=person.roles.all())
            | Q(approver_type=ApproverType.DEPARTMENT_HEAD, instance__request__department__head=person)
        )
    steps = ApprovalStep.objects.filter(
        status=StepStatus.PENDING, instance__status=InstanceStatus.IN_PROGRESS
    ).filter(mine)
    if not SystemConfig.load().allow_self_approval:
        steps = steps.exclude(instance__request__requester=user)
    return steps


def _handler_label(step, req):
    if step.approver_type == ApproverType.USER:
        who = step.user.display_name
    elif step.approver_type == ApproverType.ROLE:
        who = step.role.name
    else:
        who = req.department.head.display_name if req.department.head_id else "Department Head"
    return step.name if who == step.name else f"{step.name} · {who}"


def _skippable(step, req):
    # A department head cannot note their own request; that step falls to the next approver.
    return step.approver_type == ApproverType.DEPARTMENT_HEAD and req.department.head_id == req.requester_id


def _no_approver_error(step):
    return ValidationError(
        f'No eligible approver is available for the "{step.name}" step. Please contact an administrator.'
    )


def start(req, workflow, actor):
    """Open a new approval cycle for a request from a workflow template."""
    steps = list(workflow.steps.select_related("role", "user", "level"))
    if not steps:
        raise ValidationError(f'The "{workflow.name}" workflow has no approval steps configured.')

    instance = ApprovalInstance.objects.create(
        request=req,
        workflow=workflow,
        workflow_name=workflow.name,
        requires_ops_processing=workflow.requires_ops_processing,
        cycle=req.approval_instances.count() + 1,
    )
    snapshot = ApprovalStep.objects.bulk_create(
        ApprovalStep(
            instance=instance,
            order=s.order,
            name=s.name,
            level_name=s.level.name if s.level_id else "",
            approver_type=s.approver_type,
            role=s.role,
            user=s.user,
            after_ops=s.after_ops and workflow.requires_ops_processing,
        )
        for s in steps
    )
    # Fail at submission, not halfway through, if the route cannot be completed.
    decidable = 0
    for step in snapshot:
        if eligible_approvers(step, req):
            decidable += 1
        elif not _skippable(step, req):
            raise _no_approver_error(step)
    if decidable == 0:
        raise ValidationError(
            "This request has no independent approver in its workflow. Please contact an administrator."
        )
    _advance(instance, req, actor)
    return instance


def _awaiting_status(step):
    """The request status while this step is pending."""
    if not step.after_ops:
        return Status.PENDING_APPROVAL
    if step.role_id and step.role.code == Role.FINANCE:
        return Status.FOR_FINANCE
    return Status.INTERNAL_APPROVAL


def _hand_to_ops(req, actor, now):
    """The approvals that come before OPS are done: OPS receives and processes next."""
    previous = req.status
    req.approved_at = now
    req.status, req.current_handler = Status.APPROVED, "OPS"
    req.save(update_fields=["status", "current_handler", "approved_at", "updated_at"])
    audit.log(None, "FULLY_APPROVED", f"{req.display_number} was approved and sent to OPS",
              request=req, previous_status=previous, new_status=req.status)
    notifications.notify(Event.REQUEST_APPROVED, [req.requester, req.prepared_by], req, actor=actor)
    ops_users = User.objects.filter(roles__code=Role.OPS, is_active=True)
    notifications.notify(Event.OPS_ACTION_REQUIRED, ops_users, req, actor=actor)


def has_post_ops_steps(req):
    """True while approvals are still due after OPS finishes processing."""
    return ApprovalStep.objects.filter(
        instance__request=req, instance__status=InstanceStatus.IN_PROGRESS, status=StepStatus.WAITING, after_ops=True
    ).exists()


def resume_after_ops(req, actor):
    """OPS has finished processing: start the approvals that follow it."""
    instance = req.approval_instances.filter(status=InstanceStatus.IN_PROGRESS).first()
    if instance is None:
        raise ValidationError("This request has no approvals waiting after OPS processing.")
    _advance(instance, req, actor, after_ops=True)


def _advance(instance, req, actor, after_ops=False):
    """Activate the next step, hand over to OPS, or finish the cycle when none remain.

    Steps marked "after OPS" wait until OPS has processed the request; `after_ops`
    says that has happened.
    """
    now = timezone.now()
    ops_still_due = instance.requires_ops_processing and not after_ops
    for step in instance.steps.filter(status=StepStatus.WAITING).select_related("role", "user"):
        if step.after_ops and ops_still_due:
            _hand_to_ops(req, actor, now)
            return
        approvers = eligible_approvers(step, req)
        if not approvers:
            if not _skippable(step, req):
                raise _no_approver_error(step)
            step.status = StepStatus.SKIPPED
            step.comments = "Skipped: the requester is the department head."
            step.acted_at = now
            step.save(update_fields=["status", "comments", "acted_at"])
            audit.log(None, "STEP_SKIPPED", f"{step.name} step skipped for {req.display_number}",
                      request=req, comments=step.comments)
            continue

        step.status = StepStatus.PENDING
        step.activated_at = now
        step.save(update_fields=["status", "activated_at"])
        req.status = _awaiting_status(step)
        req.current_handler = _handler_label(step, req)
        req.save(update_fields=["status", "current_handler", "updated_at"])
        notifications.notify(Event.APPROVAL_REQUIRED, approvers, req, actor=actor)
        return

    # No steps left: every approval in the route has been given.
    instance.status = InstanceStatus.APPROVED
    instance.ended_at = now
    instance.save(update_fields=["status", "ended_at"])
    if ops_still_due:
        _hand_to_ops(req, actor, now)  # a route with no approvals after OPS; OPS completes it
        return

    previous = req.status
    req.approved_at = req.approved_at or now
    req.status, req.current_handler, req.completed_at = Status.COMPLETED, "", now
    req.save(update_fields=["status", "current_handler", "approved_at", "completed_at", "updated_at"])
    audit.log(None, "COMPLETED", f"{req.display_number} received its final approval and is completed",
              request=req, previous_status=previous, new_status=req.status)
    notifications.notify(Event.REQUEST_COMPLETED, [req.requester, req.prepared_by], req, actor=actor)


_OUTCOMES = {
    # action: (step status, instance status, request status, audit code, verb, notification)
    ActionType.REJECT: (StepStatus.REJECTED, InstanceStatus.REJECTED, Status.REJECTED,
                        "REJECTED", "rejected", Event.REQUEST_REJECTED),
    ActionType.RETURN: (StepStatus.RETURNED, InstanceStatus.RETURNED, Status.RETURNED,
                        "RETURNED", "returned", Event.REQUEST_RETURNED),
}


def act(req, actor, action, comments=""):
    """Record an approver's decision on the request's current step.

    The caller must hold a row lock on `req` so two approvers cannot decide at once.
    """
    comments = (comments or "").strip()
    step = current_step(req)
    if req.status not in AWAITING_APPROVAL or step is None:
        raise ValidationError("This request is not awaiting approval.")
    if actor.pk == req.requester_id and not SystemConfig.load().allow_self_approval:
        raise PermissionDenied("You cannot act on the approval of your own request.")
    if not can_act(actor, step, req):
        raise PermissionDenied("You are not an approver for the current step of this request.")
    if action != ActionType.APPROVE and not comments:
        raise ValidationError({"comments": ["Please explain your decision so the requester knows what to do."]})
    if action == ActionType.APPROVE and not actor.signature:
        raise ValidationError({"signature": ["Add your e-signature before approving. You can upload it here or in your Settings."]})

    ApprovalAction.objects.create(
        step=step, actor=actor, actor_position=actor.position, action=action, comments=comments
    )
    people = [req.requester, req.prepared_by]

    if action == ActionType.CLARIFY:
        step.needs_clarification = True
        step.save(update_fields=["needs_clarification"])
        audit.log(actor, "CLARIFICATION_REQUESTED",
                  f"{actor.display_name} requested clarification on {req.display_number}",
                  request=req, previous_status=req.status, new_status=req.status, comments=comments)
        notifications.notify(Event.CLARIFICATION_REQUESTED, people, req, actor=actor, comments=comments)
        return step

    now = timezone.now()
    step.acted_by, step.acted_by_position, step.acted_at = actor, actor.position, now
    # Deciding as someone's out-of-office cover is recorded as such.
    named = direct_approvers(step, req)
    if all(user.pk != actor.pk for user in named):
        step.on_behalf_of = next((user for user in named if getattr(delegation.active_delegate(user), "pk", None) == actor.pk), None)
    step.comments, step.needs_clarification = comments, False
    previous = req.status

    if action == ActionType.APPROVE:
        step.status = StepStatus.APPROVED
        step.signature = signatures.snapshot(actor.signature)
        step.save()
        audit.log(actor, "APPROVED", f"{actor.display_name} approved {req.display_number} ({step.name})",
                  request=req, previous_status=previous, new_status=previous, comments=comments)
        # A step that follows OPS can only have been reached once OPS finished.
        _advance(step.instance, req, actor, after_ops=step.after_ops)
        return step

    step_status, instance_status, request_status, code, verb, event = _OUTCOMES[action]
    step.status = step_status
    step.save()
    instance = step.instance
    instance.steps.filter(status=StepStatus.WAITING).update(status=StepStatus.CANCELLED)
    instance.status, instance.ended_at = instance_status, now
    instance.save(update_fields=["status", "ended_at"])
    req.status = request_status
    req.current_handler = req.requester.display_name if action == ActionType.RETURN else ""
    req.save(update_fields=["status", "current_handler", "updated_at"])
    audit.log(actor, code, f"{actor.display_name} {verb} {req.display_number} ({step.name})",
              request=req, previous_status=previous, new_status=req.status, comments=comments)
    notifications.notify(event, people, req, actor=actor, comments=comments)
    return step


def cancel_active(req):
    """Close any open approval cycle (used when a requester cancels)."""
    now = timezone.now()
    for instance in req.approval_instances.filter(status=InstanceStatus.IN_PROGRESS):
        instance.steps.filter(status__in=[StepStatus.WAITING, StepStatus.PENDING]).update(status=StepStatus.CANCELLED)
        instance.status, instance.ended_at = InstanceStatus.CANCELLED, now
        instance.save(update_fields=["status", "ended_at"])
