"""Business rules for creating, submitting and processing requests."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.approvals import services as approvals
from apps.audit import services as audit
from apps.core.models import SystemConfig
from apps.notifications import services as notifications
from apps.notifications.models import Event
from apps.users import signatures
from apps.users.models import Role, User
from apps.workflows.services import resolve_workflow

from . import controls, selectors
from .models import (
    FINAL_STATUSES, OPS_STATUSES, Attachment, Comment, FormKind, NumberSequence, Request, RequestLine,
    RequestType, Status,
)
from .validators import validate_upload

HEADER_FIELDS = (
    "priority", "purpose", "date_needed", "payable_to", "pr_reference",
    "po_number", "rr_number", "invoice_number", "posted",
)
LINKABLE_STATUSES = (*OPS_STATUSES, Status.COMPLETED)

_OPS_HANDLER = {Status.OPS_RECEIVED: "OPS", Status.PROCESSING: "OPS", Status.FOR_FINANCE: "Finance", Status.COMPLETED: ""}
# Statuses the OPS status endpoint accepts as a target.
OPS_TARGETS = (*_OPS_HANDLER, Status.INTERNAL_APPROVAL)


def next_ops_statuses(req):
    """Where a request may be moved from its current OPS state, and by which roles.

    When the route has approvals after OPS (the President, Finance...), finishing
    processing sends the request on to them, and the last approval completes it.
    Routes without such steps keep the older hand-off: OPS completes the request
    itself, optionally passing it to Finance first.
    """
    if req.status == Status.APPROVED:
        return {Status.OPS_RECEIVED: (Role.OPS,)}
    if req.status == Status.OPS_RECEIVED:
        return {Status.PROCESSING: (Role.OPS,)}
    if req.status == Status.PROCESSING:
        if approvals.has_post_ops_steps(req):
            return {Status.INTERNAL_APPROVAL: (Role.OPS,)}
        return {Status.FOR_FINANCE: (Role.OPS,), Status.COMPLETED: (Role.OPS,)}
    if req.status == Status.FOR_FINANCE and approvals.current_step(req) is None:
        return {Status.PROCESSING: (Role.OPS, Role.FINANCE), Status.COMPLETED: (Role.OPS, Role.FINANCE)}
    return {}


def is_owner(user, req):
    return user.pk in (req.requester_id, req.prepared_by_id)


def lock(req):
    """Re-read the request with a row lock for the rest of the transaction."""
    return Request.objects.select_for_update().select_related(
        "request_type", "requester", "prepared_by", "department"
    ).get(pk=req.pk)


def overdue_q():
    """Open requests past their needed-by date, or approved but untouched beyond the OPS SLA."""
    sla_cutoff = timezone.now() - timedelta(days=SystemConfig.load().ops_sla_days)
    open_q = ~Q(status__in=[*FINAL_STATUSES, Status.DRAFT])
    late = Q(date_needed__lt=timezone.localdate()) | Q(status__in=OPS_STATUSES, approved_at__lt=sla_cutoff)
    return open_q & late


# --- Drafting ----------------------------------------------------------------

def _check_source(user, source, req):
    if source is None:
        return
    code = req.request_type.code
    if code == RequestType.LIQ:
        # A liquidation accounts for one cash advance of the same person.
        if source.request_type.code != RequestType.CA:
            raise ValidationError({"source_request": ["A liquidation must be linked to a cash advance."]})
        if source.requester_id != req.requester_id:
            raise ValidationError({"source_request": ["That cash advance belongs to someone else."]})
        if source.status not in LINKABLE_STATUSES:
            raise ValidationError({"source_request": ["Only an approved cash advance can be liquidated."]})
        other = controls.live_liquidation(source, exclude=req)
        if other is not None:
            raise ValidationError({"source_request": [f"That cash advance already has a liquidation ({other.display_number})."]})
        return
    if code == RequestType.PR or source.request_type.code != RequestType.PR:
        raise ValidationError({"source_request": ["Only a Purchase Requisition can be linked, and not to another PR."]})
    if source.status not in LINKABLE_STATUSES:
        raise ValidationError({"source_request": ["Only an approved Purchase Requisition can be linked."]})
    if not selectors.visible_to(user).filter(pk=source.pk).exists():
        raise ValidationError({"source_request": ["You do not have access to that Purchase Requisition."]})


def _replace_lines(req, lines):
    kind = req.request_type.form_kind
    req.lines.all().delete()
    rows, total = [], Decimal("0")
    for position, line in enumerate(lines):
        quantity, unit_cost = line.get("quantity"), line.get("unit_cost")
        if kind == FormKind.ITEMS:
            amount = (quantity * unit_cost).quantize(Decimal("0.01")) if quantity and unit_cost is not None else Decimal("0")
        else:
            amount, quantity, unit_cost = line.get("amount") or Decimal("0"), None, None
        total += amount
        rows.append(RequestLine(
            request=req, position=position, description=line.get("description", ""),
            remarks=line.get("remarks", ""), quantity=quantity, unit_cost=unit_cost, amount=amount,
            expense_date=line.get("expense_date") if kind == FormKind.EXPENSE else None,
            category=line.get("category") if kind == FormKind.EXPENSE else None,
        ))
    RequestLine.objects.bulk_create(rows)
    req.total_amount = total


def save_draft(user, data, req=None):
    """Create a draft or update an editable request. Completeness is checked at submit."""
    creating = req is None
    if creating:
        # Preparing a request for a colleague: it is theirs, and they are the one who submits it.
        requester = data.get("requester") or user
        department = data.get("department") or requester.department
        if department is None:
            raise ValidationError({"department": ["The requester's profile has no department. Please select one."]})
        req = Request(
            request_type=data["request_type"], requester=requester, prepared_by=user,
            department=department, created_by=user,
        )
        if req.request_type.form_kind == FormKind.EXPENSE:
            req.payable_to = requester.display_name
    else:
        if not is_owner(user, req):
            raise PermissionDenied("Only the requester can edit this request.")
        if not req.is_editable:
            raise ValidationError("This request can no longer be edited. It must be returned for revision first.")
        if data.get("department"):
            req.department = data["department"]
        if data.get("requester") and data["requester"] != req.requester:
            if user.pk != req.prepared_by_id or req.revision > 0:
                raise ValidationError({"requester": ["The requester can only be changed by whoever prepared the draft, before it is first submitted."]})
            req.requester = data["requester"]

    if "source_request" in data:
        _check_source(user, data["source_request"], req)
        req.source_request = data["source_request"]
    for field in HEADER_FIELDS:
        if field in data:
            setattr(req, field, data[field])
    if "payable_to" in data or creating:
        req.vendor = controls.match_vendor(req.payable_to)
        if req.vendor:
            req.payable_to = req.vendor.name  # the vendor's name exactly as listed
    req.updated_by = user
    req.save()
    if "lines" in data:
        _replace_lines(req, data["lines"])
        req.save(update_fields=["total_amount"])
    if creating:
        audit.log(user, "CREATED", f"{user.display_name} created a draft {req.request_type.name}",
                  request=req, new_status=req.status)
    return req


def delete_draft(user, req):
    if not is_owner(user, req):
        raise PermissionDenied("Only the requester can delete this draft.")
    if req.status != Status.DRAFT or req.revision > 0:
        raise ValidationError("Only drafts that were never submitted can be deleted. Cancel the request instead.")
    for attachment in req.attachments.all():
        attachment.file.delete(save=False)
    audit.log(user, "DRAFT_DELETED", f"{user.display_name} deleted a draft {req.request_type.name}")
    req.delete()


# --- Submission --------------------------------------------------------------

def submission_errors(req):
    """Everything that must be true before a request can enter approval."""
    errors = {}
    rtype, kind = req.request_type, req.request_type.form_kind
    lines = list(req.lines.all())
    today = timezone.localdate()

    if rtype.code == RequestType.PR and not req.date_needed:
        errors["date_needed"] = ["Date Needed is required."]
    elif req.date_needed and req.date_needed < today:
        errors["date_needed"] = ["Date Needed cannot be in the past."]
    if kind in (FormKind.PAYMENT, FormKind.EXPENSE) and not req.payable_to.strip():
        errors["payable_to"] = ["Payable To is required."]
    if kind == FormKind.EXPENSE and not req.purpose.strip():
        errors["purpose"] = ["Purpose / Business Justification is required."]
    if rtype.code == RequestType.LIQ:
        if not req.source_request_id:
            errors["source_request"] = ["Choose the cash advance this liquidation accounts for."]
        else:
            other = controls.live_liquidation(req.source_request, exclude=req)
            if other is not None:
                errors["source_request"] = [f"That cash advance already has a liquidation ({other.display_number})."]

    line_errors = []
    for number, line in enumerate(lines, start=1):
        problems = []
        if not line.description.strip():
            problems.append("Description is required.")
        if kind == FormKind.ITEMS:
            if not line.quantity or line.quantity <= 0:
                problems.append("Quantity must be greater than zero.")
        elif line.amount <= 0:
            problems.append("Amount must be greater than zero.")
        if kind == FormKind.EXPENSE:
            if not line.expense_date:
                problems.append("Expense date is required.")
            elif line.expense_date > today:
                problems.append("Expense date cannot be in the future.")
            if not line.category_id:
                problems.append("Category is required.")
        if problems:
            line_errors.append(f"Line {number}: {' '.join(problems)}")
    if not lines:
        line_errors.append("At least one item is required.")
    if line_errors:
        errors["lines"] = line_errors

    if not req.requester.signature:
        errors["signature"] = ["Add your e-signature before submitting. You can upload it here or in your Settings."]
    if rtype.requires_attachment and not req.attachments.exists():
        errors["attachments"] = [f"At least one supporting document is required for a {rtype.name}."]
    position = controls.budget_position(req)
    if controls.blocks_submission(position):
        errors["budget"] = [controls.over_budget_message(position, SystemConfig.load().currency_symbol)
                            + " Reduce the amount or ask an administrator to raise the budget."]
    return errors


def issue_number(request_type):
    year = timezone.localdate().year
    NumberSequence.objects.get_or_create(request_type=request_type, year=year)
    sequence = NumberSequence.objects.select_for_update().get(request_type=request_type, year=year)
    sequence.last_value += 1
    sequence.save(update_fields=["last_value"])
    return f"{request_type.number_prefix}-{year}-{sequence.last_value:06d}"


def describe_route(request_type, department, amount, requester):
    """The approval route a request would take, for the review screen. None if unconfigured."""
    workflow = resolve_workflow(request_type, department, amount)
    if workflow is None:
        return None
    steps = []
    for step in workflow.steps.all():
        if step.user_id:
            approver = step.user.display_name
        elif step.role_id:
            approver = step.role.name
        else:
            head = department.head if department else None
            approver = head.display_name if head else "Not assigned"
        steps.append({"order": step.order, "name": step.name, "approver": approver,
                      "level": step.level.name if step.level_id else "",
                      "after_ops": step.after_ops and workflow.requires_ops_processing})
    return {"id": workflow.id, "name": workflow.name, "steps": steps,
            "requires_ops_processing": workflow.requires_ops_processing}


def submit(user, req):
    req = lock(req)
    if not is_owner(user, req):
        raise PermissionDenied("Only the requester can submit this request.")
    if user.pk != req.requester_id:
        # Submitting applies the requester's e-signature, so nobody can do it for them.
        raise PermissionDenied(
            f"Only {req.requester.display_name} can submit this request, because it carries their signature. "
            "Send it to them to review and submit."
        )
    if not req.is_editable:
        raise ValidationError("This request has already been submitted.")
    errors = submission_errors(req)
    if errors:
        raise ValidationError(errors)
    workflow = resolve_workflow(req.request_type, req.department, req.total_amount)
    if workflow is None:
        raise ValidationError(
            "No approval workflow is configured for this type of request. Please contact an administrator."
        )

    previous, first_time = req.status, req.revision == 0
    if not req.number:
        req.number = issue_number(req.request_type)
    req.revision += 1
    req.submitted_at = timezone.now()
    req.status = Status.PENDING_APPROVAL
    req.updated_by = user
    # A resubmission starts the whole route again, OPS processing included.
    req.approved_at = req.ops_received_at = req.ops_processed_at = req.completed_at = req.ops_alerted_at = None
    if req.requester_signature:
        req.requester_signature.delete(save=False)  # replaced by the signature used for this submission
    req.requester_signature = signatures.snapshot(req.requester.signature)
    req.save()
    # What the checks found goes into the audit trail, so it is on record that it was known.
    metadata = {"workflow": workflow.name, "amount": str(req.total_amount)}
    duplicates = controls.possible_duplicates(req)
    if duplicates:
        metadata["possible_duplicates"] = [f"{other.display_number}: {reason}" for other, reason in duplicates]
    position = controls.budget_position(req)
    if position and position["over"]:
        metadata["over_budget"] = controls.over_budget_message(position)
    audit.log(user, "SUBMITTED" if first_time else "RESUBMITTED",
              f"{user.display_name} {'submitted' if first_time else 'resubmitted'} {req.number}",
              request=req, previous_status=previous, new_status=Status.PENDING_APPROVAL,
              metadata=metadata)
    approvals.start(req, workflow, user)
    if first_time:
        ops_users = User.objects.filter(roles__code=Role.OPS, is_active=True)
        notifications.notify(Event.REQUEST_SUBMITTED, ops_users, req, actor=user)
    return req


def hand_over(user, req):
    """Whoever prepared a request for a colleague tells them it is ready to review and submit."""
    if user.pk != req.prepared_by_id or user.pk == req.requester_id:
        raise PermissionDenied("Only the person who prepared a request for someone else can send it to them.")
    if not req.is_editable:
        raise ValidationError("This request has already been submitted.")
    audit.log(user, "HANDED_OVER",
              f"{user.display_name} sent a {req.request_type.name} to {req.requester.display_name} to review and submit",
              request=req, previous_status=req.status, new_status=req.status)
    notifications.notify(Event.PREPARED_FOR_YOU, [req.requester], req, actor=user)
    return req


def cancel(user, req, comments=""):
    req = lock(req)
    if not (is_owner(user, req) or user.has_role(Role.ADMIN)):
        raise PermissionDenied("Only the requester or an administrator can cancel this request.")
    if req.status not in (Status.PENDING_APPROVAL, Status.RETURNED):
        raise ValidationError("Only requests that are pending approval or returned can be cancelled.")
    previous = req.status
    approvals.cancel_active(req)
    req.status, req.current_handler, req.updated_by = Status.CANCELLED, "", user
    req.save(update_fields=["status", "current_handler", "updated_by", "updated_at"])
    audit.log(user, "CANCELLED", f"{user.display_name} cancelled {req.number}",
              request=req, previous_status=previous, new_status=req.status, comments=comments)
    return req


# --- OPS processing ----------------------------------------------------------

def can_process(user, req):
    """True if the user may move the request out of its current OPS state."""
    return any(user.has_role(*roles) for roles in next_ops_statuses(req).values())


def ops_transition(user, req, new_status, remarks=""):
    req = lock(req)
    roles = next_ops_statuses(req).get(new_status)
    if roles is None:
        raise ValidationError(
            f"A request that is {req.get_status_display()} cannot be moved to {Status(new_status).label}."
        )
    if not user.has_role(*roles):
        raise PermissionDenied("You do not have permission to update the processing status.")

    previous, now = req.status, timezone.now()
    remarks = (remarks or "").strip()
    if new_status == Status.INTERNAL_APPROVAL:
        # Processing is finished; the approvals that follow OPS take over from here.
        req.ops_processed_at, req.updated_by = now, user
        req.save(update_fields=["ops_processed_at", "updated_by", "updated_at"])
        audit.log(user, "OPS_PROCESSED",
                  f"{user.display_name} finished processing {req.number} and sent it for internal approval",
                  request=req, previous_status=previous, new_status=previous, comments=remarks)
        approvals.resume_after_ops(req, user)
        if req.status != Status.COMPLETED:
            notifications.notify(Event.STATUS_UPDATED, [req.requester, req.prepared_by], req, actor=user, comments=remarks)
        return req

    req.status, req.current_handler, req.updated_by = new_status, _OPS_HANDLER[new_status], user
    if new_status == Status.OPS_RECEIVED:
        req.ops_received_at = now
        req.ops_assignee = req.ops_assignee or user
    if new_status == Status.COMPLETED:
        req.completed_at = now
        req.ops_processed_at = req.ops_processed_at or now
    if req.ops_assignee_id and new_status in (Status.OPS_RECEIVED, Status.PROCESSING):
        req.current_handler = f"OPS · {req.ops_assignee.display_name}"
    req.save()

    audit.log(user, new_status, f"{user.display_name} moved {req.number} to {req.get_status_display()}",
              request=req, previous_status=previous, new_status=new_status, comments=remarks)
    event = {Status.OPS_RECEIVED: Event.OPS_RECEIVED, Status.COMPLETED: Event.REQUEST_COMPLETED}.get(
        new_status, Event.STATUS_UPDATED
    )
    notifications.notify(event, [req.requester, req.prepared_by], req, actor=user, comments=remarks)
    if new_status == Status.FOR_FINANCE:
        finance = User.objects.filter(roles__code=Role.FINANCE, is_active=True)
        notifications.notify(Event.STATUS_UPDATED, finance, req, actor=user, comments=remarks)
    return req


def ops_update(user, req, data):
    """Assign a processor and/or record reference numbers while OPS holds the request."""
    req = lock(req)
    if not user.has_role(Role.OPS):
        raise PermissionDenied("Only OPS can update processing details.")
    if req.status not in OPS_STATUSES:
        raise ValidationError("Processing details can only be updated while the request is with OPS.")

    changes = {}
    for field in ("po_number", "rr_number", "invoice_number", "posted", "priority"):
        if field in data and getattr(req, field) != data[field]:
            changes[field] = [str(getattr(req, field)), str(data[field])]
            setattr(req, field, data[field])
    if "ops_assignee" in data and data["ops_assignee"] != req.ops_assignee:
        assignee = data["ops_assignee"]
        if assignee is not None and not assignee.has_role(Role.OPS):
            raise ValidationError({"ops_assignee": ["The processor must be a member of OPS."]})
        changes["ops_assignee"] = [str(req.ops_assignee or ""), str(assignee or "")]
        req.ops_assignee = assignee
        if req.status in (Status.OPS_RECEIVED, Status.PROCESSING):
            req.current_handler = f"OPS · {assignee.display_name}" if assignee else "OPS"
    if changes:
        req.updated_by = user
        req.save()
        audit.log(user, "PROCESSING_UPDATED", f"{user.display_name} updated processing details of {req.number}",
                  request=req, previous_status=req.status, new_status=req.status, metadata=changes)
    return req


# --- Purchase orders ---------------------------------------------------------

PO_STATUSES = (*OPS_STATUSES, Status.COMPLETED)


def can_issue_po(user, req):
    return req.request_type.code == RequestType.PR and req.status in PO_STATUSES and user.has_role(Role.OPS)


def _next_po_number():
    year = timezone.localdate().year
    prefix = f"PO-{year}-"
    SystemConfig.objects.select_for_update().get(pk=SystemConfig.load().pk)  # one PO number at a time
    used = Request.objects.filter(po_number__startswith=prefix).values_list("po_number", flat=True)
    highest = max((int(n[len(prefix):]) for n in used if n[len(prefix):].isdigit()), default=0)
    return f"{prefix}{highest + 1:06d}"


def issue_purchase_order(user, req, supplier, terms=""):
    """Turn an approved requisition into a purchase order: supplier, terms, and a PO number if it has none."""
    req = lock(req)
    if req.request_type.code != RequestType.PR:
        raise ValidationError("Only a Purchase Requisition can become a purchase order.")
    if not user.has_role(Role.OPS):
        raise PermissionDenied("Only OPS can issue a purchase order.")
    if req.status not in PO_STATUSES:
        raise ValidationError("A purchase order can be issued once the requisition has been approved.")
    supplier = (supplier or "").strip()
    if not supplier:
        raise ValidationError({"supplier": ["Choose or type the supplier."]})
    first_time = req.po_date is None
    req.vendor = controls.match_vendor(supplier)
    req.payable_to = req.vendor.name if req.vendor else supplier
    req.po_terms = (terms or "").strip()
    req.po_number = req.po_number or _next_po_number()
    req.po_date = req.po_date or timezone.localdate()
    req.po_issued_by, req.updated_by = user, user
    req.save()
    audit.log(user, "PO_ISSUED" if first_time else "PO_UPDATED",
              f"{user.display_name} {'issued' if first_time else 'updated'} purchase order {req.po_number} for {req.number}",
              request=req, previous_status=req.status, new_status=req.status,
              metadata={"supplier": req.payable_to, "amount": str(req.total_amount)})
    return req


# --- Comments and attachments ------------------------------------------------

def add_comment(user, req, body):
    body = (body or "").strip()
    if not body:
        raise ValidationError({"body": ["Comment cannot be empty."]})
    comment = Comment.objects.create(request=req, author=user, body=body)
    audit.log(user, "COMMENTED", f"{user.display_name} commented on {req.display_number}", request=req)

    recipients = [req.requester, req.prepared_by, req.ops_assignee]
    step = approvals.current_step(req)
    if step:
        recipients += approvals.eligible_approvers(step, req)
        if step.needs_clarification and is_owner(user, req):
            step.needs_clarification = False
            step.save(update_fields=["needs_clarification"])
    if req.status != Status.DRAFT:
        notifications.notify(Event.COMMENT_ADDED, recipients, req, actor=user, comments=body)
    return comment


def can_attach(user, req):
    if is_owner(user, req) and req.is_editable:
        return True
    return req.status in OPS_STATUSES and user.has_role(Role.OPS)


def add_attachment(user, req, upload, kind):
    if not can_attach(user, req):
        raise PermissionDenied("Documents cannot be added to this request at its current stage.")
    name, content_type = validate_upload(upload)
    attachment = Attachment.objects.create(
        request=req, file=upload, original_name=name, content_type=content_type,
        size=upload.size, kind=kind, uploaded_by=user,
    )
    audit.log(user, "ATTACHMENT_ADDED", f"{user.display_name} attached {name} to {req.display_number}", request=req)
    return attachment


def delete_attachment(user, attachment):
    req = attachment.request
    if not can_attach(user, req) or attachment.uploaded_by_id != user.pk:
        raise PermissionDenied("You cannot remove this document.")
    name = attachment.original_name
    attachment.file.delete(save=False)
    attachment.delete()
    audit.log(user, "ATTACHMENT_REMOVED", f"{user.display_name} removed {name} from {req.display_number}", request=req)
