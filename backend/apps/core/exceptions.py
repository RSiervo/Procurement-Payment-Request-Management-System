from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Give every error the same shape: {"detail": str, "errors": {field: [msg]}}."""
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(getattr(exc, "message_dict", None) or exc.messages)

    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(exc, exceptions.ValidationError):
        if isinstance(data, list):
            response.data = {"detail": str(data[0]) if data else "Invalid request.", "errors": {}}
        elif isinstance(data, dict):
            non_field = data.get("non_field_errors") or data.get("detail")
            if isinstance(non_field, list):
                non_field = non_field[0] if non_field else None
            response.data = {
                "detail": str(non_field) if non_field else "Please correct the highlighted fields.",
                "errors": {k: v for k, v in data.items() if k not in ("non_field_errors", "detail")},
            }
    elif isinstance(data, dict) and "detail" in data:
        response.data = {"detail": str(data["detail"]), "errors": {}}
    return response
