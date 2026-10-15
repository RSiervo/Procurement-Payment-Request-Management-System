import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """UUID primary key plus who/when stamps. Views set created_by/updated_by."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True


class SystemConfig(TimeStampedModel):
    """Single-row table of organisation-wide settings editable by administrators."""

    company_name = models.CharField(max_length=200, default="Your Company, Inc.")
    company_address = models.CharField(max_length=300, blank=True)
    logo = models.ImageField(upload_to="branding/", null=True, blank=True)
    currency_code = models.CharField(max_length=3, default="PHP")
    currency_symbol = models.CharField(max_length=4, default="₱")
    allow_self_approval = models.BooleanField(default=False)
    ops_sla_days = models.PositiveSmallIntegerField(default=5)
    # Automations: days a step may wait before the approver is reminded, and before
    # the administrators are told. 0 switches that automation off.
    reminder_after_days = models.PositiveSmallIntegerField(default=2)
    escalate_after_days = models.PositiveSmallIntegerField(default=5)
    max_upload_mb = models.PositiveSmallIntegerField(default=10)
    # When off, going over a department budget only warns the approvers.
    block_over_budget = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return self.company_name
