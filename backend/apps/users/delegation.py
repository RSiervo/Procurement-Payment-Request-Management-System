"""Out-of-office cover: a person names someone to approve in their place for a while."""

from django.db.models import Q
from django.utils import timezone

from .models import User


def _in_window():
    return Q(delegate_until__isnull=True) | Q(delegate_until__gte=timezone.localdate())


def active_delegate(user):
    """The person currently covering for this user, or None."""
    if not user.delegate_id:
        return None
    if user.delegate_until and user.delegate_until < timezone.localdate():
        return None
    return user.delegate if user.delegate.is_active else None


def active_delegators(user):
    """People this user is currently covering for."""
    return User.objects.filter(_in_window(), delegate=user, is_active=True)
