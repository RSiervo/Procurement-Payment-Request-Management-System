from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.display_name", default="System")

    class Meta:
        model = AuditLog
        fields = ["id", "action", "message", "actor_name", "previous_status", "new_status",
                  "comments", "ip_address", "user_agent", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("show_client"):
            # IP address and device details are for administrators only.
            data.pop("ip_address")
            data.pop("user_agent")
        return data
