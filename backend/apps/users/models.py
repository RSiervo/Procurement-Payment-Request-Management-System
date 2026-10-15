import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.functional import cached_property

from apps.core.models import BaseModel, TimeStampedModel, UUIDModel


# Colour themes offered in the web app (frontend/src/styles/themes.css). The default has no code.
COLOUR_THEMES = ("indigo", "violet", "plum", "rose", "crimson", "sunset", "amber", "olive", "forest",
                 "teal", "sky", "navy", "graphite", "bronze")


class Role(UUIDModel, TimeStampedModel):
    """Roles are data, so new ones can be added without a code change.

    The codes below are the ones the application's permission checks refer to.
    """

    REQUESTER = "REQUESTER"
    APPROVER = "APPROVER"
    DEPARTMENT_HEAD = "DEPARTMENT_HEAD"
    FINANCE = "FINANCE"
    OPS = "OPS"
    ADMIN = "ADMIN"

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True)
    is_system = models.BooleanField(default=False, help_text="System roles cannot be deleted.")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ApprovalLevel(UUIDModel, TimeStampedModel):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    rank = models.PositiveSmallIntegerField(default=1, help_text="Higher rank = more senior.")

    class Meta:
        ordering = ["rank", "name"]

    def __str__(self):
        return self.name


class Department(BaseModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120, unique=True)
    head = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_departments"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create(email, password, **extra)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    employee_id = models.CharField(max_length=40, blank=True)
    position = models.CharField(max_length=120, blank=True)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="members"
    )
    approver_level = models.ForeignKey(
        ApprovalLevel, null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    roles = models.ManyToManyField(Role, blank=True, related_name="users")
    # Windows username when the account comes from Active Directory; empty for local accounts.
    directory_username = models.CharField(max_length=150, unique=True, null=True, blank=True, editable=False)
    # Colour theme chosen under Profile -> Settings; empty means the default.
    # One of COLOUR_THEMES, or a colour of the person's own as "#rrggbb".
    theme = models.CharField(max_length=20, blank=True)
    # Out-of-office cover: who approves in this person's place, and until when (empty = until switched off).
    delegate = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="covering_for")
    delegate_until = models.DateField(null=True, blank=True)
    # The person's own settings that differ from the defaults (see preferences.py).
    preferences = models.JSONField(default=dict, blank=True)
    # The person's e-signature, applied to requests they submit and steps they approve.
    signature = models.ImageField(upload_to="signatures/users/", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.get_full_name() or self.email

    @cached_property
    def role_codes(self):
        return frozenset(self.roles.values_list("code", flat=True))

    def has_role(self, *codes):
        return not self.role_codes.isdisjoint(codes)
