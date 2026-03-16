# Firebase Authentication System

This document describes the Firebase authentication setup used by the Experiment Tracking app. **Use it as the source of truth when changing auth logic** so the approval flow, domain restriction, and token handling are not broken.

## Overview

- **Provider:** Firebase Authentication (email/password).
- **Domain restriction:** Only `@addisenergy.com` emails can register and log in.
- **Approval flow:** New users submit a registration request; an admin approves it before the user can log in. Until approval, login is blocked via custom claims.
- **Backend:** Firebase Admin SDK (server-side) for token verification and user management; client-side login uses the Firebase REST API (Identity Toolkit) so Streamlit never holds user passwords.

## Architecture

| Layer | Purpose |
|-------|--------|
| **Firebase Auth** | User accounts (email/password), ID tokens, custom claims (`approved`, `role`). |
| **Firestore** | `pending_users` collection for registration requests (email, password, display_name, role, status) until an admin approves or rejects. |
| **Streamlit** | Session state holds `user` (uid, email, display_name) and `auth_token` (Firebase ID token). Login page calls REST API; protected routes verify the token via Admin SDK. |

**Important:** The app does **not** use Firebase client SDK in the browser. Login is server-side: the user submits email/password in a form; the server calls `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=API_KEY` and stores the returned `idToken` in `st.session_state.auth_token`. Token verification uses the Admin SDK in `auth.firebase_config.verify_token()`.

## Module Layout (`auth/`)

| File | Responsibility |
|------|----------------|
| **`auth/firebase_config.py`** | Load credentials (Streamlit secrets or env vars). Initialize Firebase Admin SDK once. Expose `get_firebase_config()` for client-side config (apiKey, authDomain, etc.) and `verify_token(token)` for server-side ID token verification. |
| **`auth/user_management.py`** | Firebase Auth user CRUD (`create_user`, `list_users`, `delete_user`, `update_user`), all with `@addisenergy.com` checks. Firestore-backed pending-user flow: `create_pending_user_request`, `list_pending_users`, `approve_user`, `reject_user`, `delete_request_by_email`. Approval creates the Auth user and sets custom claims. Also: `set_user_claims`, `reset_user_password`. |
| **`auth/__init__.py`** | Package marker only. |

**Frontend:** `frontend/components/auth_components.py` — `init_auth_state()`, `render_login_page()` (login + register tabs), `require_auth` decorator, `render_logout_button()`. Calls `auth.firebase_config` and `auth.user_management` as needed.

**CLI:** `scripts/manage_users.py` — User management from the command line (create, list, delete, update, pending, approve, reject, set-claims, reset-password). Imports `auth.firebase_config` first so the Admin SDK is initialized.

## Configuration

Credentials and client config come from **Streamlit secrets** first, then **environment variables**.

### Streamlit secrets (`.streamlit/secrets.toml`)

```toml
[FIREBASE]
PROJECT_ID = "your-project-id"
PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
CLIENT_EMAIL = "firebase-adminsdk-xxx@your-project.iam.gserviceaccount.com"
API_KEY = "..."           # Web API key for REST sign-in
AUTH_DOMAIN = "your-project.firebaseapp.com"
STORAGE_BUCKET = "your-project.appspot.com"
MESSAGING_SENDER_ID = "..."
APP_ID = "..."
MEASUREMENT_ID = "..."
CLIENT_ID = "..."
CLIENT_CERT_URL = "https://..."
```

### Environment variables (fallback)

Same keys with `FIREBASE_` prefix: `FIREBASE_PROJECT_ID`, `FIREBASE_PRIVATE_KEY`, `FIREBASE_CLIENT_EMAIL`, `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, etc.

**Do not** hardcode these values or commit secrets. Use `.env` (gitignored) for local dev and Streamlit Cloud (or your host) secrets for production.

### Firebase Admin SDK initialization

In `firebase_config.py`, if `firebase_admin._apps` is empty, the app builds a service-account `cred_dict` from the keys above (with `PRIVATE_KEY` having `\\n` replaced by `\n`) and calls `firebase_admin.initialize_app(cred)`. Initialization runs at import time; failures raise so the app does not start with broken auth.

## Login Flow

1. User opens app → `init_auth_state()` sets `st.session_state.user = None`, `auth_token = None`, and caches `firebase_config`.
2. If `user` is None, `render_login_page()` is shown (Login / Register tabs).
3. **Login tab:** User submits email + password. Frontend validates `@addisenergy.com`; then POSTs to `identitytoolkit.googleapis.com/.../signInWithPassword` with `apiKey`. On 200, response contains `idToken` and `localId`.
4. Server fetches Firebase user by `localId` (Admin SDK `auth.get_user(uid)`). If `user.custom_claims.get('approved')` is not truthy, show "pending approval" and do **not** set session.
5. If approved: set `st.session_state.user = { uid, email, display_name }` and `st.session_state.auth_token = idToken`, then `st.rerun()` to show the main app.
6. **Protected routes:** Before rendering protected content, the app checks `user` and (if present) can call `verify_token(auth_token)`. If verification fails, clear session and show login again.

## Registration and Approval Flow

1. **Register tab:** User enters @addisenergy.com email, password, display name, role. On submit, `create_pending_user_request()` writes a document to Firestore `pending_users` (email, password, display_name, role, status=`pending`). No Firebase Auth user exists yet.
2. **Admin:** Uses `scripts/manage_users.py` (e.g. `pending` to list, `approve <request_id>` to approve). `approve_user(request_id)` in `user_management.py` reads the pending document, calls `create_user(email, password, display_name)` (which enforces @addisenergy.com and creates the Auth user), then `auth.set_custom_user_claims(uid, { approved: True, role })`, and updates the request status to `approved`.
3. After approval, the user can log in; custom claims are checked at login as above.

**Security note:** Pending requests store the password in Firestore only until approval. In production, consider a secure alternative (e.g. one-time link to set password) instead of storing the password in a document.

## Token Verification

- **Where:** `auth.firebase_config.verify_token(token)`.
- **Behavior:** Verifies the Firebase ID token (and optionally tries `check_revoked=False` if the first attempt fails). Returns decoded token or `None`. Used in `auth_components` on protected paths to ensure the session token is still valid; if not, session is cleared and login is shown.

## User Management CLI

Run from project root (or ensure project root is on `PYTHONPATH`):

```bash
python scripts/manage_users.py <command> [args]
```

Commands: `create`, `list`, `delete`, `update`, `pending`, `approve`, `reject`, `delete-request`, `set-claims`, `reset-password`. See `scripts/manage_users.py` for exact arguments. Importing `auth.firebase_config` at the start ensures Firebase Admin is initialized before any `user_management` calls.

## Rules for AI / Maintainers

When editing auth-related code, avoid breaking the following:

1. **Domain restriction** — Registration and login must remain restricted to `@addisenergy.com`. Do not remove or relax `validate_email_domain()` or the checks in `user_management` (`create_user`, `update_user`) and in the login/register forms.
2. **Approval gate** — Login must check `user.custom_claims.get('approved')` (or equivalent) and block unapproved users. Do not allow login with only email/password without this check.
3. **Credentials** — Do not hardcode API keys, private keys, or client emails. Keep using `get_secret_or_env()` (or equivalent) and document any new keys in this file.
4. **Single initialization** — Firebase Admin should be initialized once (check `firebase_admin._apps` before `initialize_app`). New code that uses Firebase Auth or Firestore should use the existing `auth` module and not create a second app.
5. **Token handling** — The app relies on the ID token in session for verification. Clearing or not setting `auth_token` after login will break protected-route verification. Do not switch to a different token type without updating both login and `verify_token()`.
6. **Pending users** — Approval must create the user in Firebase Auth and set custom claims; reject/delete should only remove or update the Firestore document (or mark rejected), not create Auth users.
7. **Firestore collection** — The pending-users flow depends on the `pending_users` collection and its fields (`email`, `password`, `display_name`, `role`, `status`, `created_at`, `updated_at`, `approved_at`). Changing the schema or collection name should be reflected here and in `user_management.py`.

## References

- **Auth module:** `auth/firebase_config.py`, `auth/user_management.py`
- **UI and session:** `frontend/components/auth_components.py`
- **App entry:** `app.py` (calls `init_auth_state()`, then checks `st.session_state.user` to show login vs main app)
- **CLI:** `scripts/manage_users.py`
- **Tests:** `tests/test_firebase_config.py`
