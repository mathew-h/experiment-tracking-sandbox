# Auth Hardening (Pre-Cloud-Migration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Firebase login safe to expose on the public internet. The backend must reject any token whose user was not approved by an admin, and the system must never store a password in plaintext.

**Architecture:** `_decode_token` enforces the `approved: True` custom claim, which approval already sets: invalid tokens get 401, unapproved tokens get 403. Registration stops collecting a password. Approval creates the Firebase user with a random throwaway password and generates a password-setup (reset) link for the admin to send. A CLI command removes the `password` field from existing Firestore docs. The frontend force-refreshes the ID token on load and signs out users whose token lacks the claim. Turning off self sign-up in the Firebase console adds a second layer.

**Tech Stack:** FastAPI, firebase-admin (Auth + Firestore), click CLI, React 18 + Firebase Web SDK, pytest, vitest.

**Spec:** No separate spec. The decisions were made in conversation on 2026-11-12 (Mat). They are recorded in "Decisions" below, and the current-state auth reference is `.claude/rules/AUTH.md`.

## Decisions

- D1. An unapproved but validly signed token returns **403** `"Account not approved"`. Invalid or missing tokens still return **401**. Only the literal `True` counts as approved.
- D2. Registration no longer takes a password. Approval creates the user with `secrets.token_urlsafe(32)` and returns a Firebase password-reset link. The admin sends that link to the user, and it doubles as the "set your password" link.
  - Rejected alternative: create a disabled Auth user at registration time. That breaks AUTH.md rule 2 ("no Auth account before approval").
- D3. `POST /api/auth/register` silently ignores a `password` field if one is sent (Pydantic's default `extra="ignore"`), so a stale cached frontend keeps working and its password is never stored.
- D4. The CLI `create` command stops taking a password argument. Instead it sets `approved`/`role` claims and prints a setup link, the same as `approve`. Passwords no longer go into shell history.
- D5. Out of scope: `check_revoked=True`, role-based authorization (users still pick their own role at registration; claims stay informational apart from `approved`), IP or device allowlisting, and a "Forgot password" link in the UI.

## Global Constraints

- Firebase auth is a locked component (`docs/LOCKED_COMPONENTS.md`). Mat explicitly authorized this plan's scope on 2026-11-12. Do not change anything outside it.
- The `@addisenergy.com` domain checks stay in all three places: `RegisterRequest`, `create_user`/`update_user`, and the client `RegisterForm`.
- No new Python or npm packages.
- Never import `auth.firebase_config` from backend code.
- Use structlog, never `print()`, in backend code (the CLI uses `click.echo`).
- Run pytest with `.venv/Scripts/python -m pytest`, one process at a time (shared test DB).
- Frontend: `npm run lint` and `npm run type-check` must exit 0. No `console.log`. Use brand tokens only.
- Commit format: `[#<issue>] <imperative, <50 chars>` plus the Tests/Docs lines (CLAUDE.md §7). File the GitHub issue during `/start-task` and use the branch `fix/issue-<n>-auth-hardening`.

## Review Focus

1. **Stale frontend still sends `password` to `/register`.** Expected: 201, and the password is neither forwarded nor stored. Test in Task 2: `test_register_ignores_legacy_password_field`.
2. **Token issued before the claims backfill (no `approved` in the cached token).** Expected: on app load the frontend force-refreshes and picks up the new claim, so the user is not locked out. Test in Task 4: `forces a token refresh when reading claims`.
3. **`approved` is truthy but not `True`** (`"true"`, `1`). Expected: 403. Test in Task 1: `test_decode_token_rejects_non_boolean_approved`.
4. **Pending request created under the old code (doc has `password`) is approved under the new code.** Expected: the stored password is ignored, a random one is used, and the field is deleted. Test in Task 2: `test_approve_user_ignores_and_deletes_legacy_password`.
5. **Reset-link generation fails after the Auth user was created.** Expected: approval still succeeds (user exists, claims set) and the CLI tells the admin to run `reset-password <email>`. Tests in Task 2 (`test_approve_user_link_failure_returns_none`) and Task 3 (`test_approve_without_link_prints_fallback`).

---

### Task 1: Enforce the `approved` claim in token verification

**Files:**
- Modify: `backend/auth/firebase_auth.py` (`_decode_token`)
- Test: `tests/api/test_firebase_auth.py`

**Interfaces:**
- Produces: `_decode_token(token: str) -> FirebaseUser`. It raises `HTTPException(401)` on a verification failure and `HTTPException(403, detail="Account not approved")` when `decoded.get("approved") is not True`. `verify_firebase_token` and `FirebaseUser` keep their signatures.

- [ ] **Step 1: Write the failing tests.** Update `test_decode_token_returns_firebase_user` so its mock includes `"approved": True`, then add:

```python
@pytest.mark.parametrize("claims", [{}, {"approved": False}])
def test_decode_token_rejects_unapproved(claims):
    decoded = {"uid": "u1", "email": "x@addisenergy.com", **claims}
    with patch("backend.auth.firebase_auth._verify_id_token", return_value=decoded):
        with pytest.raises(HTTPException) as exc:
            _decode_token("t")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Account not approved"

@pytest.mark.parametrize("value", ["true", 1])
def test_decode_token_rejects_non_boolean_approved(value):
    ...  # same shape as above with {"approved": value}; expect 403

def test_verify_dependency_rejects_unapproved():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="t")
    with patch("backend.auth.firebase_auth._verify_id_token",
               return_value={"uid": "u1", "email": "x@addisenergy.com"}):
        with pytest.raises(HTTPException) as exc:
            verify_firebase_token(creds)
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/api/test_firebase_auth.py -v`. Expected: the new tests FAIL (no exception raised) and the updated happy-path test passes.
- [ ] **Step 3: Implement.** In `_decode_token`, after a successful verify, add `if decoded.get("approved") is not True:` → `log.warning("token_not_approved", uid=...)` and raise 403. Keep this outside the existing `try/except`, so the 403 is not turned into a 401.
- [ ] **Step 4: Run** the same command plus `tests/api -q`. Expected: all PASS. API tests override `verify_firebase_token` in `tests/api/conftest.py`, so none should change.
- [ ] **Step 5: Update docs.** In `.claude/rules/AUTH.md`:
  - "Token Verification": add the 403 rule.
  - "Login Flow" step 6: add the 403 rule.
  - Rule 8: `approved` is now enforced in `_decode_token`; `role` is still informational.
  - Remove the "There is no explicit approved check" sentence.
- [ ] **Step 6: Commit** `[#<n>] Reject tokens without approved claim`.

### Task 2: Stop storing passwords; approval issues a setup link

**Files:**
- Modify: `backend/api/schemas/auth.py` (drop `password` and `password_min_length`)
- Modify: `backend/api/routers/auth.py` (stop passing a password; new response message)
- Modify: `auth/user_management.py` (`create_pending_user_request`, `approve_user`, `list_users`; new `purge_pending_passwords`)
- Create: `tests/test_user_management.py`
- Create: `tests/api/test_auth_register.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `create_pending_user_request(email: str, display_name: str, role: str) -> dict`. The doc has no `password` key.
  - `approve_user(request_id: str) -> dict`. Returns the `create_user` dict plus `"role": str` and `"password_setup_link": str | None`. It creates the user with `secrets.token_urlsafe(32)` and never reads the doc's `password`. The `request_ref.update(...)` call includes `"password": firestore.DELETE_FIELD`. Link-generation errors are caught and give `None`.
  - `purge_pending_passwords() -> int`. Streams every `pending_users` doc and deletes the `password` field where present. Returns how many docs it changed.
  - `list_users()` dicts gain `"custom_claims": dict` (`user.custom_claims or {}`).
  - Response message: `"Request submitted — once your lab admin approves it, you'll receive a link to set your password."`

- [ ] **Step 1: Write failing tests** in `tests/test_user_management.py`. Patch `auth.user_management.firestore` and `auth.user_management.auth` with MagicMocks, and patch `auth.user_management.create_user`.
  - `test_create_pending_request_stores_no_password`: the dict passed to `.add()` has no `"password"` key.
  - `test_approve_user_ignores_and_deletes_legacy_password`: the doc contains `"password": "hunter22"`. Assert `create_user` was called with a `password` that is not `"hunter22"` and is ≥ 32 chars; the `update` call includes `"password": <mock firestore>.DELETE_FIELD`; `set_custom_user_claims` was called with `{"approved": True, "role": "researcher"}`; the result contains `password_setup_link` equal to the mocked `generate_password_reset_link` return value.
  - `test_approve_user_link_failure_returns_none`: `generate_password_reset_link` raises. The result's `password_setup_link is None`, and claims were still set.
  - `test_purge_pending_passwords_counts_only_docs_with_password`: three streamed docs, two with `password`. Returns 2, and `update` is called twice with `DELETE_FIELD`.
- [ ] **Step 2: Write failing tests** in `tests/api/test_auth_register.py` using the `client` fixture from `tests/api/conftest.py`. Patch `backend.api.routers.auth._ensure_firebase_initialized` and `auth.user_management.create_pending_user_request`.
  - `test_register_without_password_returns_201`: body `{email, display_name, role}` returns 201, and the mock is called with exactly `email=…, display_name=…, role=…`.
  - `test_register_ignores_legacy_password_field`: the same body plus `"password": "x"` returns 201, and the `password` kwarg is not in the mock's call kwargs.
  - `test_register_rejects_non_addis_domain`: returns 422 (guards the domain check).
- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest tests/test_user_management.py tests/api/test_auth_register.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** the Interfaces above. Use `firestore.DELETE_FIELD` and `import secrets`. `auth/user_management.py` has no logger, so on a link failure return `None` without logging; the CLI reports it (Task 3). Leave the `@addisenergy.com` check in `create_user` untouched.
- [ ] **Step 5: Run** the Step 3 command. Expected: PASS.
- [ ] **Step 6: Update docs.** In `.claude/rules/AUTH.md`:
  - Registration and Approval Flow steps 2–3: no password; approval returns a setup link.
  - Delete the "Security note".
  - Rule 7: field list without `password`; mention `purge_pending_passwords`.
  - `backend/api/routers/auth.py` row: password validation removed.
- [ ] **Step 7: Commit** `[#<n>] Stop storing passwords in pending_users`.

### Task 3: CLI — approval link, passwordless create, audit and purge commands

**Files:**
- Modify: `scripts/manage_users.py`
- Test: `tests/test_manage_users_cli.py`

**Interfaces:**
- Consumes: Task 2's `approve_user` (`password_setup_link`), `purge_pending_passwords`, `list_users` (`custom_claims`), and the existing `set_user_claims` and `reset_user_password`.
- Produces these CLI commands:
  - `approve <request_id>`: prints `Approved: <email> (uid: <uid>)` and then either `Password setup link (send to user): <link>` or, when the link is `None`, `Could not generate setup link — run: manage_users.py reset-password <email>`.
  - `create <email> <display_name> [--role researcher|admin]` (default `researcher`, no password argument): creates the user with a random password, calls `set_user_claims(uid, role)`, and prints the setup link from `reset_user_password(email)`.
  - `audit-claims`: prints one line per user, `OK      <uid>  <email>` or `MISSING <uid>  <email>` (where `custom_claims.get("approved") is not True`), then `<n> user(s) missing approved claim`. Exits 1 if n > 0, otherwise 0.
  - `purge-passwords`: prints `Removed password from <n> pending request(s).`

- [ ] **Step 1: Write failing tests** following the file's existing pattern (`_import_cli`, `CliRunner`, patching `scripts.manage_users.<name>`):
  - `test_approve_prints_setup_link`
  - `test_approve_without_link_prints_fallback`: asserts `reset-password` and the email appear in the output.
  - `test_create_sets_claims_and_prints_link`: `set_user_claims` called with `(uid, role="researcher")`; `create_user` called with a generated password ≥ 32 chars.
  - `test_create_rejects_unknown_role`: exit code ≠ 0.
  - `test_audit_claims_flags_missing`: users `[{approved: True}, {}]`, exit 1, output contains `MISSING` and `1 user(s)`.
  - `test_audit_claims_all_ok`: exit 0.
  - `test_purge_passwords_reports_count`.
  - Update any existing `create` test to the new argument shape.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_manage_users_cli.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the commands. Use `click.Choice(["researcher", "admin"])` for `--role`. Update the module docstring's usage block.
- [ ] **Step 4: Run** the Step 2 command. Expected: PASS.
- [ ] **Step 5: Update docs.** In `.claude/rules/AUTH.md`, "User Management CLI": list `audit-claims` and `purge-passwords`, and the new `create` signature.
- [ ] **Step 6: Commit** `[#<n>] Add claim audit and password purge CLI`.

### Task 4: Frontend — passwordless request form, approved-claim gate

**Files:**
- Modify: `frontend/src/pages/Login.tsx` (`RegisterForm`: remove the password state, input and payload key; `LoginForm`: show `authError`)
- Modify: `frontend/src/auth/AuthContext.tsx`
- Create: `frontend/src/auth/__tests__/AuthContext.test.tsx`
- Create: `frontend/src/pages/__tests__/Login.test.tsx`

**Interfaces:**
- Consumes: the Task 1 server contract (403 = not approved). Nothing is imported from it.
- Produces: `AuthContextValue` gains `authError: string | null`. In `onAuthStateChanged`, a signed-in user's token is read with `firebaseUser.getIdTokenResult(true)`. If `result.claims.approved !== true`, the context sets `authError = "Your account has not been approved yet. Contact your lab admin."`, calls `firebaseSignOut(auth)` and leaves `user` null. Otherwise it sets `token = result.token` as today. `signIn` clears `authError` first.

- [ ] **Step 1: Write failing tests.**
  - In `AuthContext.test.tsx`, mock `firebase/auth` and `../firebaseConfig` (`firebaseConfigured: true`) and capture the `onAuthStateChanged` callback.
    - `forces a token refresh when reading claims`: `getIdTokenResult` is called with `true`.
    - `signs out and sets authError when approved claim missing`.
    - `sets Authorization header when approved`.
  - In `Login.test.tsx`:
    - `register form has no password field`: no element with `autocomplete="new-password"`.
    - `register request body has no password`: mock `apiClient.post` and assert the payload keys are exactly `email, display_name, role`.
    - `login form shows authError from context`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/auth src/pages/__tests__/Login.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement** the Interfaces above. The 55-minute refresh interval is unchanged.
- [ ] **Step 4: Run** the Step 2 command, then `npm run lint && npm run type-check`. Expected: PASS, exit 0.
- [ ] **Step 5: Update docs.** In `.claude/rules/AUTH.md`, Login Flow step 3 and the frontend paragraph: forced refresh plus the claim check.
- [ ] **Step 6: Commit** `[#<n>] Gate frontend on approved claim`.

### Task 5: Rollout runbook (Mat, manual — order matters)

No code. Add this as a `## Rollout` section in the issue log for #<n>, and tick it off as each step is done.

- [ ] **Step 1 (before deploy):** from the branch, run `.venv/Scripts/python scripts/manage_users.py audit-claims`. For every `MISSING` user who should keep access, including `labpc@addisenergy.com`, run `set-claims <uid> researcher` (or `admin`). Re-run the audit and expect exit 0. If this is skipped, those users get 403 on every API call after the deploy.
- [ ] **Step 2:** merge, then deploy via `/deploy`. Users with a tab already open may see 403s until they reload, because the reload forces a token refresh.
- [ ] **Step 3: Firebase console.** Go to Authentication → Settings → User actions and untick "Enable create (sign-up)". Verify: a `POST https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=<VITE_FIREBASE_API_KEY>` with a test email returns `ADMIN_ONLY_OPERATION`.
- [ ] **Step 4:** run `manage_users.py purge-passwords`, then run it again. Expected second result: `Removed password from 0 pending request(s).`
- [ ] **Step 5: Smoke test.** Submit a request from the UI, approve it via the CLI, open the setup link, set a password and sign in. Expected: the app loads, and the Firestore doc has no `password` field.
