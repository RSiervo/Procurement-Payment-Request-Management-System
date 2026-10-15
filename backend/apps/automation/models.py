from django.db import models


class JobState(models.Model):
    """Whether an automation is switched on, and how its last run went."""

    OK, SKIPPED, FAILED = "ok", "skipped", "failed"

    key = models.CharField(max_length=40, primary_key=True)
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=10, blank=True)
    last_detail = models.CharField(max_length=500, blank=True)
    running_since = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.key
