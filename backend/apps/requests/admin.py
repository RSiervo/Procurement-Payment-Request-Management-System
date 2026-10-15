from django.contrib import admin

from .models import Attachment, Budget, Comment, ExpenseCategory, Request, RequestLine, RequestType, Vendor


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class LineInline(ReadOnlyInline):
    model = RequestLine
    fields = ["position", "description", "remarks", "quantity", "unit_cost", "amount", "expense_date", "category"]


class AttachmentInline(ReadOnlyInline):
    model = Attachment
    fields = ["original_name", "kind", "size", "uploaded_by", "created_at"]
    readonly_fields = ["created_at"]


class CommentInline(ReadOnlyInline):
    model = Comment
    fields = ["author", "body", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    """Requests are view-only here: status changes must go through the workflow so that
    approvals, notifications and the audit trail stay consistent."""

    list_display = ["display_number", "request_type", "requester", "department", "status", "total_amount", "created_at"]
    list_filter = ["status", "request_type", "department"]
    search_fields = ["number", "requester__email", "requester__first_name", "requester__last_name"]
    date_hierarchy = "created_at"
    inlines = [LineInline, AttachmentInline, CommentInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RequestType)
class RequestTypeAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "number_prefix", "form_kind", "requires_attachment", "is_active"]
    readonly_fields = ["code", "form_kind"]


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ["name", "tin", "is_active"]
    search_fields = ["name", "tin"]


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ["department", "year", "amount"]
    list_filter = ["year"]


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
