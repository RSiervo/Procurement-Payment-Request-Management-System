import re

from django.contrib.auth import password_validation
from django.db import transaction
from rest_framework import serializers

from . import preferences
from .models import COLOUR_THEMES, ApprovalLevel, Department, Role, User


class RoleSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Role
        fields = ["id", "code", "name", "description", "is_system", "user_count"]
        read_only_fields = ["is_system"]

    def validate_code(self, value):
        value = value.upper()
        if self.instance and self.instance.is_system and value != self.instance.code:
            raise serializers.ValidationError("The code of a system role cannot be changed.")
        return value


class ApprovalLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalLevel
        fields = ["id", "code", "name", "rank"]

    def validate_code(self, value):
        return value.upper()


class DepartmentSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(source="head.display_name", read_only=True, default="")
    member_count = serializers.IntegerField(source="members.count", read_only=True)

    class Meta:
        model = Department
        fields = ["id", "code", "name", "head", "head_name", "is_active", "member_count"]


class UserBriefSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name")
    department_name = serializers.CharField(source="department.name", default="")

    class Meta:
        model = User
        fields = ["id", "name", "email", "position", "department_name"]


class UserSerializer(serializers.ModelSerializer):
    """Administrator view of a user account."""

    name = serializers.CharField(source="display_name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default="")
    approver_level_name = serializers.CharField(source="approver_level.name", read_only=True, default="")
    roles = serializers.SlugRelatedField(slug_field="code", queryset=Role.objects.all(), many=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, style={"input_type": "password"})
    is_directory_user = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "name", "employee_id", "position",
            "department", "department_name", "approver_level", "approver_level_name",
            "roles", "is_active", "last_login", "password", "is_directory_user", "directory_username",
        ]
        read_only_fields = ["last_login", "directory_username"]
        extra_kwargs = {"first_name": {"required": True, "allow_blank": False},
                        "last_name": {"required": True, "allow_blank": False}}

    def get_is_directory_user(self, user):
        return bool(user.directory_username)

    def validate_email(self, value):
        return value.lower()

    def validate_password(self, value):
        if value and self.instance is not None and self.instance.directory_username:
            raise serializers.ValidationError("This account signs in with Active Directory; its password is managed there.")
        if value:
            password_validation.validate_password(value, self.instance)
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "A password is required for a new user."})
        return attrs

    @transaction.atomic
    def create(self, validated):
        roles, password = validated.pop("roles", []), validated.pop("password")
        user = User.objects.create_user(password=password, **validated)
        user.roles.set(roles)
        return user

    @transaction.atomic
    def update(self, user, validated):
        roles, password = validated.pop("roles", None), validated.pop("password", "")
        for field, value in validated.items():
            setattr(user, field, value)
        if password:
            user.set_password(password)
        user.save()
        if roles is not None:
            user.roles.set(roles)
        return user


class MeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default="")
    approver_level_name = serializers.CharField(source="approver_level.name", read_only=True, default="")
    roles = serializers.SerializerMethodField()
    heads_department = serializers.SerializerMethodField()
    has_signature = serializers.SerializerMethodField()
    is_directory_user = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "name", "employee_id", "position",
            "department", "department_name", "approver_level_name", "roles", "heads_department", "has_signature", "theme",
            "is_directory_user", "preferences",
        ]
        read_only_fields = ["email", "employee_id", "position", "department"]

    def validate_theme(self, value):
        value = value.strip().lower()
        if value and value not in COLOUR_THEMES and not re.fullmatch(r"#[0-9a-f]{6}", value):
            raise serializers.ValidationError("Choose one of the listed themes or a colour such as #2160e0.")
        return value

    def get_roles(self, user):
        return sorted(user.role_codes)

    def get_heads_department(self, user):
        return user.headed_departments.exists()

    def get_has_signature(self, user):
        return bool(user.signature)

    def get_is_directory_user(self, user):
        return bool(user.directory_username)

    def get_preferences(self, user):
        return preferences.for_user(user)


class LoginSerializer(serializers.Serializer):
    # Named "email" for compatibility; a Windows username is accepted too.
    email = serializers.CharField(max_length=254)
    password = serializers.CharField(trim_whitespace=False)
    remember = serializers.BooleanField(required=False, default=False)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value
