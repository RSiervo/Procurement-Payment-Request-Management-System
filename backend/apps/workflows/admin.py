from django.contrib import admin

from .models import Workflow, WorkflowStep


class StepInline(admin.TabularInline):
    model = WorkflowStep
    extra = 0
    fields = ["order", "name", "level", "approver_type", "role", "user"]
    autocomplete_fields = ["user"]


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ["name", "request_type", "department", "min_amount", "max_amount", "priority", "is_active"]
    list_filter = ["request_type", "is_active"]
    exclude = ["created_by", "updated_by"]
    inlines = [StepInline]
