from django.template import TemplateSyntaxError
from rest_framework import serializers

from . import services
from .defaults import PLACEHOLDERS
from .models import Notification, NotificationTemplate


class NotificationSerializer(serializers.ModelSerializer):
    request_number = serializers.CharField(source="request.display_number", default="")

    class Meta:
        model = Notification
        fields = ["id", "event", "title", "message", "request", "request_number", "is_read", "created_at"]


class RequestNotificationSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(source="recipient.display_name")

    class Meta:
        model = Notification
        fields = ["id", "event", "title", "recipient_name", "email_status", "emailed_at", "created_at"]


class NotificationTemplateSerializer(serializers.ModelSerializer):
    event_display = serializers.CharField(source="get_event_display", read_only=True)
    placeholders = serializers.SerializerMethodField()

    class Meta:
        model = NotificationTemplate
        fields = ["id", "event", "event_display", "subject", "body", "send_email", "is_active", "placeholders"]
        read_only_fields = ["event"]

    def get_placeholders(self, obj):
        return PLACEHOLDERS

    def _check(self, value):
        try:
            services.validate_template(value)
        except TemplateSyntaxError as exc:
            raise serializers.ValidationError(f"Template error: {exc}")
        return value

    validate_subject = _check
    validate_body = _check
