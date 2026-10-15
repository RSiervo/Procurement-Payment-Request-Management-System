import django_filters
from django.db.models import Q

from apps.approvals.services import pending_steps_for

from . import services
from .models import OPS_STATUSES, Request, Status


class RequestFilter(django_filters.FilterSet):
    type = django_filters.CharFilter(field_name="request_type__code")
    status = django_filters.BaseInFilter(field_name="status")
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    min_amount = django_filters.NumberFilter(field_name="total_amount", lookup_expr="gte")
    max_amount = django_filters.NumberFilter(field_name="total_amount", lookup_expr="lte")
    scope = django_filters.CharFilter(method="filter_scope")
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    unassigned = django_filters.BooleanFilter(field_name="ops_assignee", lookup_expr="isnull")

    class Meta:
        model = Request
        fields = ["department", "requester", "priority", "ops_assignee"]

    def filter_scope(self, queryset, name, value):
        user = self.request.user
        mine = Q(requester=user) | Q(prepared_by=user)
        if value == "mine":
            return queryset.filter(mine)
        if value == "drafts":
            return queryset.filter(mine, status=Status.DRAFT)
        if value == "awaiting_me":
            return queryset.filter(approval_instances__steps__in=pending_steps_for(user)).distinct()
        if value == "ops":
            return queryset.filter(status__in=OPS_STATUSES)
        return queryset

    def filter_overdue(self, queryset, name, value):
        return queryset.filter(services.overdue_q()) if value else queryset
