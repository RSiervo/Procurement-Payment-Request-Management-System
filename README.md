# Procurement & Payment Portal

Internal web application that replaces the paper Purchase Requisition (PR), Request for
Payment (RFP) and reimbursement forms with one digital workflow: create, approve, process,
track, print.

- `backend/` — Django 5.2 + Django REST Framework + PostgreSQL
- `frontend/` — Vite + React 19 + TypeScript

## Running it locally

### 1. Database

Any PostgreSQL 14+ database works. Put its URL in `backend/.env`.

On this machine the app uses the `rms_portal` database on the main PostgreSQL server
(`127.0.0.1:5432`), which runs as a Windows service and starts with the computer.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py bootstrap --admin-email you@company.com   # roles, request types, templates, first admin
.venv\Scripts\python manage.py runserver 127.0.0.1:8010
```

`bootstrap` is safe to re-run. It prints a one-time password for the administrator it creates
(or uses `ADMIN_PASSWORD` from the environment).

Optional demo data (departments, 11 users, workflows, sample requests; `DEBUG=True` only):

```powershell
.venv\Scripts\python manage.py seed_demo --password "choose-a-password"
```

### 3. Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5180, proxies /api to the backend on 8010
```

The web server listens on all network interfaces, so other devices on the same network can open
`http://<this-computer's-IP>:5180`. For that, add the IP to `ALLOWED_HOSTS` in `backend/.env`, set
`FRONTEND_URL` to that address, and allow inbound TCP 5180 in Windows Firewall. Set `PORT` or
`API_TARGET` to use different ports.

The npm scripts call the tools through `node` directly. npm's `.cmd` shims break when a parent
folder name contains `&`, as this one does, so use `npm run …` rather than `npx vite`.

### Checks

```powershell
cd backend;  .venv\Scripts\python manage.py test tests     # 125 API and workflow tests
cd frontend; npm run build; npm run lint
```

## How it works

**One request model.** `Request` holds what every form shares (number, requester, department,
status, total, reference numbers). `RequestType` says which line layout a type uses (items,
payment particulars, or expenses), and `RequestLine` stores the lines. PR, RFP and reimbursement
are three rows in `RequestType`, not three sets of tables.

**Configurable approval routes.** A `Workflow` is a list of steps plus the rule for when it
applies: request type, optional department, optional amount range (both ends inclusive), and a
priority for ties. A department-specific workflow beats a general one. Each step is approved by
the head of the request's department, anyone holding a role, or a named user.

**Snapshots.** Submitting copies the matching workflow's steps into an `ApprovalInstance`.
Editing a workflow never changes requests already in approval. Returning a request closes the
instance; resubmitting opens a new one, so earlier decisions stay on record.

**Status lifecycle.**

```
DRAFT → PENDING_APPROVAL → APPROVED → OPS_RECEIVED → PROCESSING → INTERNAL_APPROVAL → FOR_FINANCE → COMPLETED
              ├→ RETURNED → (edit) → PENDING_APPROVAL
              ├→ REJECTED
              └→ CANCELLED
```

The usual route is requester → department head → OPS receives and processes → internal approval
(for example the President) → Finance, whose approval completes the request. A workflow step is
marked "before OPS" or "after OPS"; steps after OPS wait until OPS has finished processing. The
request number is issued on first submission, so abandoned drafts leave no gaps in the sequence.

**E-signatures.** Each person uploads or draws a signature (Settings). It is required to submit
and to approve; a copy is kept with the request or step at that moment, and printed on the form.

**Out-of-office cover.** A person can name a colleague to approve in their place (Settings). The
cover signs with their own signature and the history records that they acted on behalf of the
other person. Nobody can approve their own request this way.

**Checks on each request** (`apps/requests/controls.py`), shown to everyone handling it and
recorded in the audit trail at submission:
- *Possible duplicate payment* — same payee and invoice number, or same payee and amount within
  60 days.
- *Budget* — where the request leaves the department's budget for the year (Administration →
  Budgets). Warns by default; Administration → System can make it stop the submission.
- *Unlisted payee* — a payment to someone not in the vendor list (Administration → Vendors).

**Cash advances.** A Cash Advance (CA) asks for money before it is spent; a Liquidation (LIQ)
accounts for one advance with receipts and works out what is returned or reimbursed. An advance
takes one liquidation, and a new advance shows the requester's earlier ones still outstanding.
Both types are switched off by default. To use them, activate them under Administration →
Request Types and give each an approval workflow (Administration → Approval Workflows).

**Requesting for a colleague.** The preparer fills in the request and sends it to the requester,
who reviews and submits it: submitting applies the requester's signature, so nobody can do it for them.

**Purchase orders.** OPS issues a numbered purchase order (PO-YYYY-000001) from an approved
requisition by naming the supplier; `apps/requests/purchase_order.py` prints it.

**Also:** approvers can approve several requests at once (each is still recorded separately);
local accounts can reset a forgotten password by emailed link (one hour, single use); request
lists export to Excel; administrators can search and export the whole audit log.

**Test copies.** To run a second copy against another database, set `DATABASE_URL`, `MEDIA_ROOT`,
`FRONTEND_URL` and `EMAIL_DISABLED=True` in the environment. `EMAIL_DISABLED` matters: without it
the copy uses the mail server in `.env`.

**Printed forms** carry a QR code that opens `/verify/<id>`: a public page showing the number,
status, amount and sign-offs, so a paper copy can be checked without an account. It never shows
items, attachments or comments.

## Automations

`manage.py run_automations` runs whichever jobs are due; schedule it every 15 minutes (on this
machine: the Windows scheduled task "PPMS Automations", output in `.local/logs/scheduled.log`).
Each job keeps its own timetable and can be switched off or run by hand under Administration →
Automations.

| Job | When | What it does |
|---|---|---|
| Approval reminders | hourly | Reminds an approver after the reminder days, repeating |
| Approval escalation | hourly | Tells administrators once when a step waits past the escalation days |
| OPS overdue alerts | hourly | Alerts OPS once per request past the OPS target days |
| Daily summary email | 8 AM | What is waiting for each person; nothing if nothing is waiting |
| Active Directory sync | 1 AM | Refreshes accounts, deactivates leavers; skipped if the directory is unreachable |
| Backup | midnight | Database and uploads to `.local/backups/auto`, last 14 kept |
| Monthly report | 1st, 7 AM | Last month's summary and spreadsheet to administrators and Finance |

`run_automations --list` shows them; `--job <key> --force` runs one now.

## Installing as an app

The frontend is an installable web app (`public/manifest.webmanifest`, `public/sw.js`). Browsers
only offer installation over HTTPS or on `localhost`, so it appears for other devices once the
portal is served over HTTPS with a certificate they trust. Nothing is cached offline; the
service worker only provides a "cannot reach the portal" page.

**Where the rules live.** Business logic is in service modules, not in serializers or React:

| Module | Responsibility |
|---|---|
| `apps/approvals/services.py` | Who may decide a step, what each decision does |
| `apps/requests/services.py` | Drafting, submission checks, numbering, OPS transitions, attachments |
| `apps/requests/selectors.py` | Which requests a user may see |
| `apps/requests/controls.py` | Duplicate, budget and vendor checks |
| `apps/automation/jobs.py`, `runner.py` | The scheduled jobs and when each is due |
| `apps/reports/services.py` | Dashboard and Reports figures, exports |
| `apps/users/directory.py`, `delegation.py` | Active Directory sign-in and sync; out-of-office cover |
| `apps/workflows/services.py` | Choosing the workflow for a request |
| `apps/notifications/services.py` | In-app notifications and email |
| `apps/requests/pdf.py` | Printable forms |

**Security.**
- Session cookie authentication (HttpOnly) with CSRF protection; no tokens in browser storage.
- Every list and detail endpoint filters by what the user may see; other requests return 404.
- Self-approval is blocked on the server unless an administrator enables it.
- Uploads are checked by extension, size and file signature, stored under random names, and
  served only through an authenticated endpoint.
- Every significant action is written to an append-only audit log.

## Active Directory sign-in

With the `AUTH_LDAP_*` settings filled in (`backend/.env`), people sign in with their Windows
username or email and their Windows password. The password is checked by the directory and is
never stored by the portal.

- **Account sync.** On each sign-in the portal account's name, email, position and department
  are refreshed from the directory. The department is the person's own OU.
- **Roles from OUs.** Anyone beneath an OU named in `AUTH_LDAP_ADMIN_OUS` becomes a portal
  administrator and may use Django admin. `AUTH_LDAP_ROLE_OUS` maps further roles the same way.
  Roles granted by hand in the portal (Finance, OPS, Approver) are kept; only OU-driven roles
  are added and removed automatically.
- **Local accounts.** Accounts created in Django admin or the portal's Users screen keep their
  own password and still work, including when the directory is unreachable.
- **Check the connection** without changing anything:
  `.venv\Scripts\python manage.py ldap_check some.username`

Django admin is at `http://127.0.0.1:8010/django-admin/` and is reachable only from the server
itself; the web server forwards `/api` only.
## Configuration

All settings come from environment variables (`backend/.env`); each one is explained by a comment in that file.
With `EMAIL_HOST` empty, emails are printed to the server console instead of being sent.

For production: set `DEBUG=False`, a real `SECRET_KEY`, `ALLOWED_HOSTS` and `FRONTEND_URL`; serve
`frontend/dist` and proxy `/api` to Django from the same HTTPS origin; run Django under a WSGI
server (for example gunicorn or waitress).

## Known limits

- **Email is sent in the request cycle**, right after the database commit. If the mail server
  cannot be reached the portal gives up after a few seconds, marks those emails failed and does
  not try the server again for 5 minutes. Failed emails are not retried later; the in-app
  notification is always kept.
- **Leaving a half-filled request form** asks for confirmation when a link is clicked or the tab
  is closed. The browser's Back button is not intercepted.
- **The verification page is public** to anyone who can reach the portal and has the form's QR
  code (requests are identified by a random id, and lookups are limited to 30 a minute).
- **Login rate limiting** (10 per minute per address) uses Django's per-process cache. Configure
  a shared cache such as Redis when running more than one server process.
- **No self-service password reset.** Administrators set passwords from the Users screen.
- **Workflow rules** match on type, department and amount. Routing by individual requester is
  not implemented.
- **New request types** need a developer: each type must use one of the three line layouts or
  add a new one.
- **Requests are always raised by the signed-in user**; preparing a request on someone else's
  behalf is not supported.
- **The printed forms** follow the field lists of the paper forms. Compare them against the
  originals and adjust `apps/requests/pdf.py` where the layout should differ.
- **Client IP in the audit log** is the connecting address. Behind a reverse proxy, configure the
  proxy to pass the real address.
