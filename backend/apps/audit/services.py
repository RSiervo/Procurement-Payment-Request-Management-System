from .middleware import get_client_info
from .models import AuditLog


def log(actor, action, message, *, request=None, previous_status="", new_status="", comments="", metadata=None):
    ip, user_agent = get_client_info()
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        request=request,
        message=message[:300],
        previous_status=previous_status or "",
        new_status=new_status or "",
        comments=comments or "",
        metadata=metadata or {},
        ip_address=ip,
        user_agent=user_agent,
    )
