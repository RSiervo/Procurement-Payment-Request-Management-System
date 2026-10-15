"""Each person's own settings (Settings page in the web app).

Only values that differ from the defaults are stored on the user; reading always
returns the full set, so new settings can be added without touching existing accounts.
"""

from rest_framework import serializers

DEFAULTS = {
    # Email. In-app notifications are always created; these only control the email copy.
    "email_action": True,     # something is waiting for me: approvals, questions, returned requests
    "email_updates": True,    # progress on requests I am involved in
    "email_comments": True,   # new comments
    "email_digest": True,     # the morning summary of what is waiting for me
    # Display
    "density": "auto",        # auto | compact | comfortable
    "motion": "on",           # on | off
    "page_size": 20,          # rows per page in request lists
    "landing": "dashboard",   # first page after signing in
}

# Which setting governs the email for each notification event (apps.notifications.models.Event).
_EMAIL_SETTING = {
    "APPROVAL_REQUIRED": "email_action",
    "OPS_ACTION_REQUIRED": "email_action",
    "CLARIFICATION_REQUESTED": "email_action",
    "REQUEST_RETURNED": "email_action",
    "PREPARED_FOR_YOU": "email_action",
    "APPROVAL_REMINDER": "email_action",
    "APPROVAL_ESCALATED": "email_action",
    "OPS_OVERDUE": "email_action",
    "COMMENT_ADDED": "email_comments",
}


class PreferencesSerializer(serializers.Serializer):
    email_action = serializers.BooleanField(required=False)
    email_updates = serializers.BooleanField(required=False)
    email_comments = serializers.BooleanField(required=False)
    email_digest = serializers.BooleanField(required=False)
    density = serializers.ChoiceField(choices=["auto", "compact", "comfortable"], required=False)
    motion = serializers.ChoiceField(choices=["on", "off"], required=False)
    page_size = serializers.ChoiceField(choices=[10, 20, 50], required=False)
    landing = serializers.ChoiceField(choices=["dashboard", "requests", "approvals"], required=False)


def for_user(user):
    """The person's settings with defaults filled in. Unknown stored keys are ignored."""
    stored = user.preferences if isinstance(user.preferences, dict) else {}
    return {key: stored.get(key, default) for key, default in DEFAULTS.items()}


def update(user, data):
    """Validate and merge a partial change; returns the full settings."""
    serializer = PreferencesSerializer(data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    merged = {**for_user(user), **serializer.validated_data}
    user.preferences = {key: value for key, value in merged.items() if value != DEFAULTS[key]}
    user.save(update_fields=["preferences", "updated_at"])
    return merged


def wants_email(user, event):
    """Whether this person wants an email for this kind of notification."""
    return bool(for_user(user)[_EMAIL_SETTING.get(str(event), "email_updates")])
