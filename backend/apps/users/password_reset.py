"""Self-service password reset for local accounts.

People who sign in with Active Directory change their password in Windows, so they are
told that instead of being sent a link. The response is the same whether or not the
address belongs to an account, so the form cannot be used to find out who has one.
"""

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit

from .models import User

LINK_HOURS = settings.PASSWORD_RESET_TIMEOUT // 3600


def request_reset(email):
    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None:
        return
    if user.directory_username:
        body = (
            f"Hello {user.first_name or user.display_name},\n\n"
            "Someone asked to reset your password for the Procurement & Payment Portal.\n\n"
            "You sign in to the portal with your Windows (Active Directory) account, so there is no separate "
            "portal password. Change or reset your Windows password the usual way, or ask IT for help.\n\n"
            "If this was not you, you can ignore this message."
        )
    else:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={default_token_generator.make_token(user)}"
        body = (
            f"Hello {user.first_name or user.display_name},\n\n"
            "Someone asked to reset your password for the Procurement & Payment Portal. "
            f"To choose a new password, open this link within {LINK_HOURS} hour{'s' if LINK_HOURS != 1 else ''}:\n\n"
            f"{link}\n\n"
            "The link works once. If this was not you, ignore this message and your password stays as it is."
        )
    audit.log(user, "PASSWORD_RESET_REQUESTED", f"A password reset was requested for {user.email}")
    send_mail("Reset your password - Procurement & Payment Portal", body, None, [user.email], fail_silently=True)


def confirm_reset(uid, token, new_password):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError, DjangoValidationError):
        user = None
    if user is None or user.directory_username or not default_token_generator.check_token(user, token):
        raise ValidationError("This reset link is no longer valid. Ask for a new one from the sign-in page.")
    try:
        password_validation.validate_password(new_password, user)
    except DjangoValidationError as exc:
        raise ValidationError({"new_password": list(exc.messages)}) from None
    user.set_password(new_password)  # also invalidates the link and every signed-in session
    user.save(update_fields=["password"])
    audit.log(user, "PASSWORD_RESET", f"{user.display_name} reset their password by emailed link")
    return user
