"""Active Directory sign-in.

People sign in with their Windows username (or email) and password. The password is
checked by binding to the directory as that person; it is never stored here. On every
sign-in the account's name, email, position, department and directory-driven roles are
refreshed from the directory.

Accounts created locally (Django admin or the portal's Users screen) are untouched and
keep signing in with their own password through Django's ModelBackend.
"""

import logging
import re
import ssl
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.db import transaction
from ldap3 import SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import parse_dn

from .models import Department, Role, User

logger = logging.getLogger(__name__)

# Enabled people only: bit 2 of userAccountControl marks a disabled account.
_PERSON_FILTER = "(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2))"
_ATTRIBUTES = ["sAMAccountName", "userPrincipalName", "mail", "givenName", "sn", "displayName", "title", "employeeID"]


@dataclass
class DirectoryEntry:
    dn: str
    username: str
    email: str
    first_name: str = ""
    last_name: str = ""
    position: str = ""
    employee_id: str = ""
    ous: list[str] = field(default_factory=list)  # nearest first: department, division, site

    @property
    def department(self):
        return self.ous[0] if self.ous else ""


def is_configured():
    return bool(settings.AUTH_LDAP_SERVER_URI and settings.AUTH_LDAP_BIND_DN and settings.AUTH_LDAP_BIND_PASSWORD)


def _server():
    uri = settings.AUTH_LDAP_SERVER_URI
    tls = None
    if uri.lower().startswith("ldaps://"):
        tls = Tls(
            validate=ssl.CERT_REQUIRED if settings.AUTH_LDAP_VERIFY_CERT else ssl.CERT_NONE,
            ca_certs_file=settings.AUTH_LDAP_CA_CERT_FILE or None,
        )
    return Server(uri, tls=tls, connect_timeout=8)


def _connect(user, password):
    return Connection(_server(), user=user, password=password, auto_bind=True, receive_timeout=10, read_only=True)


def _first(entry, name):
    value = entry["attributes"].get(name)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _to_entry(raw):
    ous = [value for attribute, value, _ in parse_dn(raw["dn"]) if attribute.upper() == "OU"]
    username = _first(raw, "sAMAccountName")
    email = (_first(raw, "mail") or _first(raw, "userPrincipalName")).lower()
    first, last = _first(raw, "givenName"), _first(raw, "sn")
    if not (first or last):
        first = _first(raw, "displayName")
    return DirectoryEntry(dn=raw["dn"], username=username.lower(), email=email, first_name=first, last_name=last,
                          position=_first(raw, "title"), employee_id=_first(raw, "employeeID"), ous=ous)


def find(login):
    """Look a person up by Windows username, user principal name or email. None if absent."""
    value = escape_filter_chars(login.strip())
    query = f"(&{_PERSON_FILTER}(|(sAMAccountName={value})(userPrincipalName={value})(mail={value})))"
    with _connect(settings.AUTH_LDAP_BIND_DN, settings.AUTH_LDAP_BIND_PASSWORD) as connection:
        for base in settings.AUTH_LDAP_USER_SEARCH_BASES:
            connection.search(base, query, search_scope=SUBTREE, attributes=_ATTRIBUTES, size_limit=2)
            people = [e for e in connection.response if e.get("type") == "searchResEntry"]
            if len(people) == 1:
                return _to_entry(people[0])
            if len(people) > 1:
                logger.warning("Directory sign-in for %r matched more than one account; refusing.", login)
                return None
    return None


def search(term, limit=8):
    """People whose name, username or email contains the text. Used to pick a colleague who has no portal account yet."""
    value = escape_filter_chars(term.strip())
    if len(value) < 2:
        return []
    query = (f"(&{_PERSON_FILTER}(|(displayName=*{value}*)(givenName={value}*)(sn={value}*)"
             f"(sAMAccountName={value}*)(mail={value}*)))")
    found = {}
    with _connect(settings.AUTH_LDAP_BIND_DN, settings.AUTH_LDAP_BIND_PASSWORD) as connection:
        for base in settings.AUTH_LDAP_USER_SEARCH_BASES:
            connection.search(base, query, search_scope=SUBTREE, attributes=_ATTRIBUTES, size_limit=limit)
            for raw in connection.response:
                if raw.get("type") == "searchResEntry":
                    entry = _to_entry(raw)
                    if entry.username and entry.email:
                        found.setdefault(entry.username, entry)
    return list(found.values())[:limit]


def check_password(dn, password):
    """True if the directory accepts this password for this person."""
    # An empty password would be an anonymous bind, which Active Directory accepts.
    if not password:
        return False
    try:
        _connect(dn, password).unbind()
    except LDAPException:
        return False
    return True


# --- Mapping the directory onto portal accounts --------------------------------

def _matches(entry_ous, wanted):
    names = {name.casefold() for name in entry_ous}
    return any(item.casefold() in names for item in wanted)


def roles_for(entry):
    """Role codes the directory decides for this person: {code: should_have}."""
    mapping = {Role.ADMIN: settings.AUTH_LDAP_ADMIN_OUS, **settings.AUTH_LDAP_ROLE_OUS}
    return {code: _matches(entry.ous, ous) for code, ous in mapping.items() if ous}


def _department_code(name):
    """A short unique code such as ITSO for "IT SECURITY OPERATIONS"."""
    words = re.findall(r"[A-Za-z0-9]+", name)
    base = ("".join(word[0] for word in words) if len(words) > 1 else name[:8]).upper()[:16] or "DEPT"
    code, suffix = base, 2
    while Department.objects.filter(code=code).exists():
        code, suffix = f"{base}{suffix}", suffix + 1
    return code


def _department(name):
    if not name:
        return None
    existing = Department.objects.filter(name__iexact=name).first()
    return existing or Department.objects.create(name=name, code=_department_code(name))


@transaction.atomic
def sync_user(entry):
    """Create or refresh the portal account for a directory person."""
    user = User.objects.filter(directory_username=entry.username).first()
    if user is None:
        # Adopt an existing local account with the same email rather than duplicating the person.
        user = User.objects.filter(email=entry.email).first() or User(email=entry.email)
    elif entry.email != user.email and not User.objects.filter(email=entry.email).exclude(pk=user.pk).exists():
        user.email = entry.email

    creating = user._state.adding
    if creating:
        user.set_unusable_password()  # the directory holds the password
    user.directory_username = entry.username
    user.first_name, user.last_name = entry.first_name, entry.last_name
    user.position = entry.position
    user.employee_id = entry.employee_id or user.employee_id
    user.department = _department(entry.department) or user.department

    decided = roles_for(entry)
    is_admin = decided.get(Role.ADMIN, False)
    # Directory administrators may also use Django admin (for creating local accounts).
    user.is_staff = user.is_superuser = is_admin
    user.save()

    # Only roles the directory decides are added or removed; anything an administrator
    # granted by hand (Finance, OPS, Approver...) is left as it is.
    grant = [code for code, wanted in decided.items() if wanted]
    revoke = [code for code, wanted in decided.items() if not wanted]
    if creating:
        grant.append(Role.REQUESTER)
    user.roles.add(*Role.objects.filter(code__in=grant))
    user.roles.remove(*Role.objects.filter(code__in=revoke))
    user.__dict__.pop("role_codes", None)  # drop the cached role set
    return user


class ActiveDirectoryBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not (is_configured() and username and password):
            return None
        try:
            entry = find(username)
            if entry is None or not entry.email or not check_password(entry.dn, password):
                return None
            user = sync_user(entry)
        except LDAPException as exc:
            # Directory unreachable or misconfigured: fall through to local accounts.
            logger.error("Active Directory sign-in unavailable: %s", exc)
            return None
        return user if user.is_active else None

    def get_user(self, user_id):
        return User.objects.filter(pk=user_id, is_active=True).first()
