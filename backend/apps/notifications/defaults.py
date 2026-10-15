"""Built-in wording for each notification event.

`bootstrap` copies these into NotificationTemplate rows, where administrators can
edit them. They are also the fallback if a row is missing.
"""

from .models import Event

PLACEHOLDERS = [
    "request_number", "request_type", "requester", "department", "amount", "status",
    "current_level", "date_submitted", "date_needed", "total_items", "actor",
    "actor_position", "comments", "action_date", "recipient_name", "company_name",
]

DEFAULT_TEMPLATES = {
    Event.REQUEST_SUBMITTED: (
        "New {{ request_type }} Submitted — {{ request_number }}",
        "A new {{ request_type }} has been submitted and is now in approval. "
        "It will come to OPS for processing once approved.",
    ),
    Event.APPROVAL_REQUIRED: (
        "Approval Required — {{ request_number }}",
        "{{ request_type }} {{ request_number }} requires your approval.",
    ),
    Event.REQUEST_APPROVED: (
        "Approved — {{ request_number }}",
        "Your {{ request_type }} {{ request_number }} has been fully approved and sent to OPS for processing.",
    ),
    Event.REQUEST_REJECTED: (
        "Rejected — {{ request_number }}",
        "Your {{ request_type }} {{ request_number }} was rejected by {{ actor }} on {{ action_date }}.\n\n"
        "Reason: {{ comments }}",
    ),
    Event.REQUEST_RETURNED: (
        "Returned for Revision — {{ request_number }}",
        "Your {{ request_type }} {{ request_number }} was returned for revision by {{ actor }} on {{ action_date }}.\n\n"
        "Comments: {{ comments }}\n\nPlease update the request and resubmit it.",
    ),
    Event.CLARIFICATION_REQUESTED: (
        "Clarification Requested — {{ request_number }}",
        "{{ actor }} needs more information before deciding on {{ request_type }} {{ request_number }}.\n\n"
        "Question: {{ comments }}\n\nReply in the request's comments.",
    ),
    Event.OPS_ACTION_REQUIRED: (
        "Ready for Processing — {{ request_number }}",
        "{{ request_type }} {{ request_number }} has been fully approved and requires OPS processing.",
    ),
    Event.OPS_RECEIVED: (
        "Received by OPS — {{ request_number }}",
        "OPS has received your {{ request_type }} {{ request_number }} and will begin processing it.",
    ),
    Event.STATUS_UPDATED: (
        "Status Update — {{ request_number }}",
        "Your {{ request_type }} {{ request_number }} is now: {{ status }}.\n\n{{ comments }}",
    ),
    Event.REQUEST_COMPLETED: (
        "Completed — {{ request_number }}",
        "Your {{ request_type }} {{ request_number }} has been completed.\n\n{{ comments }}",
    ),
    Event.COMMENT_ADDED: (
        "New Comment — {{ request_number }}",
        "{{ actor }} commented on {{ request_type }} {{ request_number }}:\n\n{{ comments }}",
    ),
    Event.APPROVAL_REMINDER: (
        "Reminder: {{ request_number }} is waiting for your approval",
        "{{ request_type }} {{ request_number }} from {{ requester }} is still waiting for your approval. "
        "Please review it when you can.",
    ),
    Event.APPROVAL_ESCALATED: (
        "Approval overdue: {{ request_number }}",
        "{{ request_type }} {{ request_number }} from {{ requester }} ({{ department }}) has been waiting at the "
        "{{ current_level }} step longer than the allowed time. Please follow up with the approver.",
    ),
    Event.PREPARED_FOR_YOU: (
        "{{ actor }} prepared a {{ request_type }} for you",
        "{{ actor }} prepared a {{ request_type }} in your name. Please review it; if it is correct, "
        "submit it, which applies your e-signature and sends it for approval.\n\n{{ comments }}",
    ),
    Event.OPS_OVERDUE: (
        "Processing overdue: {{ request_number }}",
        "{{ request_type }} {{ request_number }} was approved and has not been processed within the target time. "
        "Please attend to it.",
    ),
}