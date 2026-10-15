from django.contrib import admin

from apps.approvals.models import ApprovalAction, ApprovalInstance, ApprovalStep
from apps.core.models import SystemConfig
from apps.notifications.models import Notification, NotificationTemplate

from .models import AuditLog


class ReadOnlyAdmin(admin.ModelAdmin):
    """History records can be inspected but never altered from the admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdmin):
    list_display = ["created_at", "actor", "action", "message", "ip_address"]
    list_filter = ["action"]
    search_fields = ["message", "actor__email"]
    date_hierarchy = "created_at"


class ApprovalStepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0
    can_delete = False
    fields = ["order", "name", "status", "acted_by", "acted_at", "comments"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ApprovalInstance)
class ApprovalInstanceAdmin(ReadOnlyAdmin):
    list_display = ["request", "cycle", "workflow_name", "status", "started_at", "ended_at"]
    list_filter = ["status"]
    inlines = [ApprovalStepInline]


@admin.register(ApprovalAction)
class ApprovalActionAdmin(ReadOnlyAdmin):
    list_display = ["created_at", "actor", "action", "step", "comments"]
    list_filter = ["action"]


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ["created_at", "recipient", "event", "title", "email_status"]
    list_filter = ["event", "email_status"]
    search_fields = ["title", "recipient__email"]


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ["event", "subject", "send_email", "is_active"]
    readonly_fields = ["event"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    exclude = ["updated_by"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
