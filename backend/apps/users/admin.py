from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import ApprovalLevel, Department, Role, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Email is the sign-in name, so the stock username-based layout is replaced."""

    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "department", "directory_username", "is_active", "is_staff"]
    list_filter = ["is_active", "is_staff", "department", "roles"]
    search_fields = ["email", "first_name", "last_name", "employee_id"]
    filter_horizontal = ["roles"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Profile", {"fields": ["first_name", "last_name", "employee_id", "position", "department", "approver_level"]}),
        ("Access", {"fields": ["roles", "is_active", "is_staff", "is_superuser"]}),
        ("Dates", {"fields": ["last_login", "date_joined"]}),
        ("Active Directory", {"fields": ["directory_username"],
                              "description": "Filled in when the person signs in with their Windows account. "
                                             "Empty for accounts created here, which sign in with the password above."}),
    ]
    readonly_fields = ["directory_username"]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["email", "first_name", "last_name", "password1", "password2"]}),
    ]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "head", "is_active"]
    search_fields = ["code", "name"]
    autocomplete_fields = ["head"]
    exclude = ["created_by", "updated_by"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_system"]


@admin.register(ApprovalLevel)
class ApprovalLevelAdmin(admin.ModelAdmin):
    list_display = ["rank", "name", "code"]
