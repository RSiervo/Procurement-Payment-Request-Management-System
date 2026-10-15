from unittest import mock

from django.test import override_settings
from ldap3.core.exceptions import LDAPSocketOpenError

from apps.users import directory
from apps.users.directory import DirectoryEntry
from apps.users.models import Department, Role, User

from .base import PortalTestCase

AD = dict(
    AUTH_LDAP_SERVER_URI="ldaps://ad.example.test",
    AUTH_LDAP_BIND_DN="svc@example.test",
    AUTH_LDAP_BIND_PASSWORD="service-secret",
    AUTH_LDAP_USER_SEARCH_BASES=["OU=Makati,DC=example,DC=test"],
    AUTH_LDAP_ADMIN_OUS=["IT SECURITY OPERATIONS"],
    AUTH_LDAP_ROLE_OUS={"FINANCE": ["BILLING AND COLLECTION"]},
)


def person(username="rostom.siervo", department="IT SECURITY OPERATIONS", division="INFORMATION AND COMMUNICATIONS TECHNOLOGY", **extra):
    values = dict(
        dn=f"CN={username},OU={department},OU={division},OU=Makati,DC=example,DC=test",
        username=username, email=f"{username}@example.test", first_name="Rostom", last_name="Siervo",
        position="Process Automation Developer", ous=[department, division, "Makati"],
    )
    return DirectoryEntry(**{**values, **extra})


@override_settings(**AD)
class DirectorySignInTests(PortalTestCase):
    def sign_in(self, login, password, entry, accepted=True):
        with mock.patch.object(directory, "find", return_value=entry) as find, \
             mock.patch.object(directory, "check_password", return_value=accepted):
            response = self.client.post("/api/auth/login/", {"email": login, "password": password}, format="json")
        return response, find

    def test_first_sign_in_creates_the_account_from_the_directory(self):
        response, find = self.sign_in("Rostom.Siervo", "windows-password", person())
        self.assertEqual(response.status_code, 200, response.data)
        find.assert_called_once_with("rostom.siervo")

        user = User.objects.get(directory_username="rostom.siervo")
        self.assertEqual(user.email, "rostom.siervo@example.test")
        self.assertEqual(user.display_name, "Rostom Siervo")
        self.assertEqual(user.position, "Process Automation Developer")
        self.assertEqual(user.department.name, "IT SECURITY OPERATIONS")
        self.assertEqual(user.department.code, "ISO")
        self.assertFalse(user.has_usable_password())  # the password stays in the directory
        self.assertEqual(user.role_codes, {Role.ADMIN, Role.REQUESTER})
        self.assertTrue(user.is_staff and user.is_superuser)  # may use Django admin
        self.assertEqual(sorted(response.data["roles"]), [Role.ADMIN, Role.REQUESTER])

    def test_people_outside_the_admin_ou_are_plain_requesters(self):
        self.sign_in("ana", "pw", person("ana", department="MARKETING", division="OPERATIONS"))
        user = User.objects.get(directory_username="ana")
        self.assertEqual(user.role_codes, {Role.REQUESTER})
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(self.client.get("/api/users/").status_code, 403)

    def test_admin_ou_matches_at_any_depth_and_ignores_case(self):
        entry = person("lead", department="SOC TEAM", division="It Security Operations")
        self.sign_in("lead", "pw", entry)
        self.assertIn(Role.ADMIN, User.objects.get(directory_username="lead").role_codes)

    def test_extra_role_mapping_and_hand_granted_roles(self):
        self.sign_in("bea", "pw", person("bea", department="BILLING AND COLLECTION", division="OPERATIONS"))
        bea = User.objects.get(directory_username="bea")
        self.assertEqual(bea.role_codes, {Role.FINANCE, Role.REQUESTER})

        # An administrator grants OPS by hand; she later moves to another department.
        bea.roles.add(Role.objects.get(code=Role.OPS))
        self.sign_in("bea", "pw", person("bea", department="MARKETING", division="OPERATIONS"))
        bea = User.objects.get(directory_username="bea")
        self.assertEqual(bea.role_codes, {Role.OPS, Role.REQUESTER})  # FINANCE removed, OPS kept
        self.assertEqual(bea.department.name, "MARKETING")

    def test_leaving_the_admin_ou_removes_admin_access(self):
        self.sign_in("rostom.siervo", "pw", person())
        self.sign_in("rostom.siervo", "pw", person(department="MARKETING", division="OPERATIONS"))
        user = User.objects.get(directory_username="rostom.siervo")
        self.assertNotIn(Role.ADMIN, user.role_codes)
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_wrong_password_is_rejected_and_creates_nothing(self):
        response, _ = self.sign_in("rostom.siervo", "wrong", person(), accepted=False)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Incorrect username or password.")
        self.assertFalse(User.objects.filter(directory_username="rostom.siervo").exists())

    def test_unknown_or_disabled_directory_account_is_rejected(self):
        response, _ = self.sign_in("ghost", "pw", None)
        self.assertEqual(response.status_code, 400)

    def test_a_deactivated_portal_account_cannot_sign_in(self):
        self.sign_in("rostom.siervo", "pw", person())
        User.objects.filter(directory_username="rostom.siervo").update(is_active=False)
        response, _ = self.sign_in("rostom.siervo", "pw", person())
        self.assertEqual(response.status_code, 400)

    def test_empty_password_never_reaches_the_directory(self):
        # Active Directory treats an empty password as an anonymous bind and accepts it.
        with mock.patch.object(directory, "_connect") as connect:
            self.assertFalse(directory.check_password("CN=x,DC=example,DC=test", ""))
        connect.assert_not_called()

    def test_local_accounts_still_work_and_survive_a_directory_outage(self):
        with mock.patch.object(directory, "find", return_value=None):
            ok = self.client.post("/api/auth/login/", {"email": "juan@example.com", "password": "S3cure-pass-phrase"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.client.post("/api/auth/logout/")
        with mock.patch.object(directory, "find", side_effect=LDAPSocketOpenError("server down")):
            ok = self.client.post("/api/auth/login/", {"email": "juan@example.com", "password": "S3cure-pass-phrase"}, format="json")
        self.assertEqual(ok.status_code, 200)

    def test_same_department_in_two_sites_is_one_department(self):
        self.sign_in("a", "pw", person("a"))
        entry = person("b")
        entry.dn = entry.dn.replace("OU=Makati", "OU=Carmona")
        self.sign_in("b", "pw", entry)
        self.assertEqual(Department.objects.filter(name__iexact="IT SECURITY OPERATIONS").count(), 1)

    def test_directory_account_password_cannot_be_set_in_the_portal(self):
        self.sign_in("rostom.siervo", "pw", person())
        user = User.objects.get(directory_username="rostom.siervo")
        response = self.as_user(self.admin).patch(f"/api/users/{user.id}/", {"password": "An0ther-long-phrase"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data["errors"])


class DirectoryDisabledTests(PortalTestCase):
    def test_without_configuration_the_directory_is_never_contacted(self):
        with mock.patch.object(directory, "find") as find:
            response = self.client.post("/api/auth/login/", {"email": "juan@example.com", "password": "S3cure-pass-phrase"}, format="json")
        self.assertEqual(response.status_code, 200)
        find.assert_not_called()
