from contextvars import ContextVar

_current_request = ContextVar("current_http_request", default=None)


def get_client_info():
    """Return (ip, user_agent) for the HTTP request being handled, if any."""
    request = _current_request.get()
    if request is None:
        return None, ""
    # REMOTE_ADDR is the peer address. Behind a reverse proxy, configure the proxy
    # (or a trusted-proxy middleware) to set it; X-Forwarded-For is not trusted here.
    return request.META.get("REMOTE_ADDR"), request.META.get("HTTP_USER_AGENT", "")[:255]


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            _current_request.reset(token)
