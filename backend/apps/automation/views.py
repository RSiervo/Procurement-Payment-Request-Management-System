from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.permissions import IsAdminRole

from . import runner
from .models import JobState


def _describe(job, state):
    return {
        "key": job.key, "name": job.name, "description": job.description, "schedule": job.schedule,
        "enabled": state.enabled, "last_run_at": state.last_run_at, "last_status": state.last_status,
        "last_detail": state.last_detail, "running": state.running_since is not None,
    }


def _job(key):
    job = runner.BY_KEY.get(key)
    if job is None:
        raise Http404
    return job, JobState.objects.get_or_create(key=key)[0]


class AutomationListView(APIView):
    """The automations, whether each is on, and how its last run went. Administrators only."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response([_describe(job, JobState.objects.get_or_create(key=job.key)[0]) for job in runner.JOBS])


class AutomationView(APIView):
    permission_classes = [IsAdminRole]

    def patch(self, request, key):
        job, state = _job(key)
        enabled = request.data.get("enabled")
        if not isinstance(enabled, bool):
            return Response({"detail": "Send enabled as true or false.", "errors": {}}, status=400)
        state.enabled = enabled
        state.save(update_fields=["enabled"])
        audit.log(request.user, "AUTOMATION_CHANGED",
                  f"{request.user.display_name} switched {job.name} {'on' if enabled else 'off'}")
        return Response(_describe(job, state))


class AutomationRunView(APIView):
    """Run one automation immediately, whatever its timetable."""

    permission_classes = [IsAdminRole]

    def post(self, request, key):
        job, _ = _job(key)
        audit.log(request.user, "AUTOMATION_RUN", f"{request.user.display_name} ran {job.name} manually")
        return Response(_describe(job, runner.run_job(job)))
