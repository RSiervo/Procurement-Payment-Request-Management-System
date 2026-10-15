from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ldap3.core.exceptions import LDAPException

from apps.users import directory


class Command(BaseCommand):
    help = "Test the Active Directory connection and show how a person would be mapped. Changes nothing."

    def add_arguments(self, parser):
        parser.add_argument("username", help="A Windows username or email to look up.")

    def handle(self, *args, **options):
        if not directory.is_configured():
            raise CommandError("Set AUTH_LDAP_SERVER_URI, AUTH_LDAP_BIND_DN and AUTH_LDAP_BIND_PASSWORD in .env first.")
        self.stdout.write(f"Server: {settings.AUTH_LDAP_SERVER_URI}")
        self.stdout.write(f"Bind account: {settings.AUTH_LDAP_BIND_DN}")
        try:
            entry = directory.find(options["username"])
        except LDAPException as exc:
            raise CommandError(f"Could not query the directory: {exc}")
        self.stdout.write(self.style.SUCCESS("Connected and signed in with the bind account."))
        if entry is None:
            raise CommandError(f"No enabled person found for {options['username']!r} under the search bases.")

        roles = [code for code, wanted in directory.roles_for(entry).items() if wanted]
        self.stdout.write(f"Found:       {entry.dn}")
        self.stdout.write(f"Username:    {entry.username}")
        self.stdout.write(f"Email:       {entry.email or '(none — this person could not sign in)'}")
        self.stdout.write(f"Name:        {entry.first_name} {entry.last_name}")
        self.stdout.write(f"Position:    {entry.position}")
        self.stdout.write(f"Department:  {entry.department}")
        self.stdout.write(f"Roles from the directory: {', '.join(roles) or 'none (Requester only)'}")
