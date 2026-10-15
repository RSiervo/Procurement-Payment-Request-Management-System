from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.users.models import Role, User

from .base import PortalTestCase

PASSWORD = "S3cure-pass-phrase"


class AuthenticationTests(PortalTestCase):
    def test_login_requires_a_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        credentials = {"email": "juan@example.com", "password": PASSWORD}
        self.assertEqual(client.post("/api/auth/login/", credentials, format="json").status_code, 403)

        token = client.get("/api/auth/csrf/").data["csrfToken"]
        response = client.post("/api/auth/login/", credentials, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["roles"], [Role.REQUESTER])
        self.assertEqual(client.get("/api/me/").data["email"], "juan@example.com")
        # Unsafe requests on an authenticated session also need the token.
        self.assertEqual(client.post("/api/auth/logout/").status_code, 403)

    def test_remember_me_controls_how_long_the_sign_in_lasts(self):
        credentials = {"email": "juan@example.com", "password": PASSWORD}
        self.client.post("/api/auth/login/", credentials, format="json")
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.client.post("/api/auth/logout/")
        self.client.post("/api/auth/login/", {**credentials, "remember": True}, format="json")
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 60 * 60 * 24 * 14)

    def test_branding_is_public_and_minimal(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/branding/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"company_name", "has_logo"})

    def test_bad_credentials_and_inactive_accounts_get_the_same_answer(self):
        User.objects.filter(pk=self.sofia.pk).update(is_active=False)
        for email, password in (("juan@example.com", "wrong"), ("sofia@example.com", PASSWORD),
                                ("nobody@example.com", PASSWORD)):
            response = self.client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["detail"], "Incorrect username or password.")
        self.assertEqual(AuditLog.objects.filter(action="LOGIN_FAILED").count(), 3)

    def test_colour_theme_is_saved_on_the_account(self):
        client = self.as_user(self.juan)
        self.assertEqual(client.get("/api/me/").data["theme"], "")
        self.assertEqual(client.patch("/api/me/", {"theme": "forest"}, format="json").data["theme"], "forest")
        self.assertEqual(client.get("/api/me/").data["theme"], "forest")
        self.assertEqual(client.patch("/api/me/", {"theme": "not-a-theme"}, format="json").status_code, 400)
        # A colour of their own is accepted as a hex code, and nothing else is.
        self.assertEqual(client.patch("/api/me/", {"theme": "#1A7F5C"}, format="json").data["theme"], "#1a7f5c")
        for bad in ("#12345", "#gggggg", "red", "#1a7f5c; background:url(x)"):
            self.assertEqual(client.patch("/api/me/", {"theme": bad}, format="json").status_code, 400)
        self.assertEqual(client.patch("/api/me/", {"theme": ""}, format="json").data["theme"], "")
        # Choosing a theme must not let someone change protected profile fields.
        client.patch("/api/me/", {"theme": "teal", "email": "other@example.com"}, format="json")
        self.assertEqual(client.get("/api/me/").data["email"], "juan@example.com")

    def test_personal_settings_are_validated_and_merged(self):
        client = self.as_user(self.juan)
        defaults = client.get("/api/me/").data["preferences"]
        self.assertEqual(defaults["page_size"], 20)
        self.assertTrue(defaults["email_action"])
        saved = client.patch("/api/me/", {"preferences": {"page_size": 50, "density": "compact"}}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual((saved.data["preferences"]["page_size"], saved.data["preferences"]["density"]), (50, "compact"))
        # A later change keeps earlier ones, and other people are unaffected.
        again = client.patch("/api/me/", {"preferences": {"motion": "off"}}, format="json").data["preferences"]
        self.assertEqual((again["page_size"], again["motion"]), (50, "off"))
        self.assertEqual(self.as_user(self.sofia).get("/api/me/").data["preferences"]["page_size"], 20)
        for bad in ({"page_size": 5000}, {"density": "huge"}, {"email_action": "sometimes"}):
            self.assertEqual(self.as_user(self.juan).patch("/api/me/", {"preferences": bad}, format="json").status_code, 400)

    def test_email_settings_decide_who_gets_an_email(self):
        from apps.notifications.models import EmailStatus, Notification

        self.as_user(self.maria).patch("/api/me/", {"preferences": {"email_action": False}}, format="json")
        pr = self.submitted_pr()  # Maria (department head) is asked to approve
        note = Notification.objects.get(recipient=self.maria, request_id=pr["id"], event="APPROVAL_REQUIRED")
        self.assertEqual(note.email_status, EmailStatus.NOT_SENT)  # still notified in the app, no email
        ops_note = Notification.objects.get(recipient=self.oscar, request_id=pr["id"], event="REQUEST_SUBMITTED")
        self.assertNotEqual(ops_note.email_status, EmailStatus.NOT_SENT)

    def test_password_change_enforces_policy(self):
        client = self.as_user(self.juan)
        weak = client.post("/api/me/change-password/",
                           {"current_password": PASSWORD, "new_password": "short"}, format="json")
        self.assertEqual(weak.status_code, 400)
        wrong = client.post("/api/me/change-password/",
                            {"current_password": "nope", "new_password": "An0ther-long-phrase"}, format="json")
        self.assertIn("current_password", wrong.data["errors"])


class AdministrationAccessTests(PortalTestCase):
    def test_configuration_endpoints_are_admin_only(self):
        read_only = ["/api/users/", "/api/workflows/", "/api/notification-templates/", "/api/email-settings/"]
        for url in read_only:
            with self.subTest(url=url):
                self.assertEqual(self.as_user(self.oscar).get(url).status_code, 403)
                self.assertEqual(self.as_user(self.admin).get(url).status_code, 200)
        for url in ("/api/departments/", "/api/roles/", "/api/expense-categories/"):
            with self.subTest(url=url):
                self.assertEqual(self.as_user(self.juan).get(url).status_code, 200)
                self.assertEqual(self.as_user(self.juan).post(url, {"name": "X", "code": "X"}).status_code, 403)
        self.assertEqual(self.as_user(self.juan).patch("/api/system-config/", {"allow_self_approval": True},
                                                       format="json").status_code, 403)

    def test_admin_manages_users_and_cannot_lock_themselves_out(self):
        client = self.as_user(self.admin)
        created = client.post("/api/users/", {
            "email": "New.User@Example.com", "first_name": "New", "last_name": "User", "password": "Str0ng-pass-phrase",
            "department": str(self.it.id), "roles": [Role.REQUESTER, Role.OPS]}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["email"], "new.user@example.com")
        self.assertNotIn("password", created.data)
        self.assertTrue(User.objects.get(email="new.user@example.com").check_password("Str0ng-pass-phrase"))

        weak = client.post("/api/users/", {"email": "w@example.com", "first_name": "W", "last_name": "W",
                                           "password": "12345678", "roles": []}, format="json")
        self.assertIn("password", weak.data["errors"])
        lockout = client.patch(f"/api/users/{self.admin.id}/", {"roles": [Role.REQUESTER]}, format="json")
        self.assertEqual(lockout.status_code, 400)
        self.assertEqual(client.delete(f"/api/users/{self.juan.id}/").status_code, 405)

    def test_admin_creates_a_workflow_with_steps(self):
        finance = Role.objects.get(code=Role.FINANCE)
        payload = {"name": "RFP high value", "request_type": "RFP", "min_amount": "100000", "priority": 5, "steps": [
            {"name": "Noted By", "approver_type": "DEPARTMENT_HEAD"},
            {"name": "Verified By", "approver_type": "ROLE", "role": str(finance.id)},
            {"name": "Approved By", "approver_type": "USER", "user": str(self.sam.id)},
        ]}
        response = self.as_user(self.admin).post("/api/workflows/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([s["order"] for s in response.data["steps"]], [1, 2, 3])
        payload["steps"][1].pop("role")
        invalid = self.as_user(self.admin).post("/api/workflows/", payload, format="json")
        self.assertEqual(invalid.status_code, 400)

    def test_self_approval_setting_is_honoured(self):
        felix = User.objects.create_user("felix@example.com", PASSWORD, first_name="Felix", department=self.it)
        felix.roles.set(Role.objects.filter(code=Role.FINANCE))  # a second, independent Finance approver
        pr = self.submitted_pr(user=self.fiona, unit_cost="12000")
        self.act(self.maria, pr["id"], "approve")
        self.assertEqual(self.act(self.fiona, pr["id"], "approve").status_code, 403)
        self.as_user(self.admin).patch("/api/system-config/", {"allow_self_approval": True}, format="json")
        self.assertEqual(self.act(self.fiona, pr["id"], "approve").status_code, 200)

    def test_audit_ip_details_are_admin_only(self):
        pr = self.submitted_pr()
        url = f"/api/requests/{pr['id']}/audit-log/"
        self.assertNotIn("ip_address", self.as_user(self.juan).get(url).data[0])
        self.assertIn("ip_address", self.as_user(self.admin).get(url).data[0])


class ReportingTests(PortalTestCase):
    def test_reports_are_restricted_and_scoped(self):
        self.submitted_pr()
        self.submitted_pr(user=self.sofia)
        self.assertEqual(self.as_user(self.juan).get("/api/reports/").status_code, 403)
        self.assertEqual(self.as_user(self.oscar).get("/api/reports/").data["totals"]["requests"], 2)
        scoped = self.as_user(self.sergio).get("/api/reports/").data
        self.assertEqual([row["label"] for row in scoped["by_department"]], ["Sales"])

    def test_exports(self):
        pr = self.submitted_pr()
        client = self.as_user(self.oscar)
        csv_response = client.get("/api/reports/export/?report=all_requests&file_format=csv")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn(pr["number"], csv_response.content.decode("utf-8-sig"))
        xlsx = client.get("/api/reports/export/?report=by_department&file_format=xlsx")
        self.assertTrue(xlsx.content.startswith(b"PK"))
        pdf = client.get("/api/reports/export/?report=by_status&file_format=pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF-"))
        self.assertEqual(client.get("/api/reports/export/?report=nope").status_code, 400)

    def test_dashboard_sections_follow_roles(self):
        self.submitted_pr()
        requester = self.as_user(self.juan).get("/api/dashboard/").data
        self.assertEqual(requester["requester"]["pending"], 1)
        self.assertIsNone(requester["ops"])
        self.assertIsNone(requester["admin"])
        self.assertEqual(self.as_user(self.maria).get("/api/dashboard/").data["approver"]["pending"], 1)
        self.assertIsNotNone(self.as_user(self.oscar).get("/api/dashboard/").data["ops"])
        self.assertEqual(self.as_user(self.admin).get("/api/dashboard/").data["admin"]["pending_approval"], 1)
