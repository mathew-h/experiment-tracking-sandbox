# Firebase Authentication System

This document describes the Firebase authentication setup used by the Experiment Tracking app. **Use it as the source of truth when changing auth logic** so the approval flow, domain restriction, and token handling are not broken.

## Overview

- **Provider:** Firebase Authentication (email/password).
- **Domain restriction:** Only `@addisenergy.com` emails can register and log in.
- **Approval flow:** New users submit a registration request via the React app; an admin approves it via CLI before the user can log in. Until approval, no Firebase Auth account exists for that email, so sign-in is impossible.
- **Login:** The React frontend uses the **Firebase Web SDK directly in the browser** — this is a client-side login, not a server-side proxy. The FastAPI backend never sees passwords; it only verifies ID tokens on protected API calls.
- **Backend:** Firebase Admin SDK (server-side) for token verification, user management, and the Firestore-backed approval queue.

## Architecture

| Layer | Purpose |
|-------|--------|
| **Firebase Auth** | User accounts (email/password), ID tokens, custom claims (`approved`, `role`). |
| **Firestore** | `pending_users` collection for registration requests (email, password, display_name, role, status) until an admin approves or rejects. |
| **React (`frontend/src/auth/`)** | Firebase Web SDK client. `AuthContext` manages the signed-in user and ID token in React state; `ProtectedRoute` gates routes. |
| **FastAPI (`backend/auth/`, `backend/api/routers/auth.py`)** | Verifies Bearer ID tokens on protected endpoints via the Admin SDK; exposes `POST /api/auth/register` to create pending requests. |

**Two separate Firebase credential surfaces exist:**
- **Backend (Admin SDK):** `.env` → `backend/config/settings.py` (`firebase_project_id`, `firebase_private_key`, `firebase_client_email`, `firebase_client_id`, `firebase_client_cert_url`).
- **Frontend (Web SDK):** `frontend/.env.local`, copied from `frontend/.env.example` (`VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_APP_ID`). Without these, `frontend/src/auth/firebaseConfig.ts` sets `firebaseConfigured = false` and the login page renders a warning instead of the form.

## Module Layout

| File | Responsibility |
|------|----------------|
| **`backend/auth/firebase_auth.py`** | Initializes Firebase Admin SDK from `backend/config/settings.py` (guarded by `firebase_admin._apps`, safe to call repeatedly). Exposes `verify_firebase_token` — the FastAPI dependency used on every protected route — which extracts the Bearer token, verifies it (`check_revoked=False`), and returns a `FirebaseUser(uid, email, display_name)`. **Does not currently surface `role`/`approved` custom claims** to route handlers — only the three fields above. |
| **`backend/api/routers/auth.py`** | `POST /api/auth/register` — the only auth endpoint. Validates the payload via `backend/api/schemas/auth.py` (email must end `@addisenergy.com`, role in `{researcher, admin}`, password ≥ 8 chars), then delegates to `auth.user_management.create_pending_user_request()`. |
| **`auth/user_management.py`** (root, **shared** — not backend-scoped) | Firebase Auth user CRUD (`create_user`, `list_users`, `delete_user`, `update_user`, all with `@addisenergy.com` checks) and the Firestore pending-user flow (`create_pending_user_request`, `list_pending_users`, `approve_user`, `reject_user`, `delete_request_by_email`). `approve_user` creates the Auth user and sets custom claims `{approved: True, role}`. Imported by `backend/api/routers/auth.py`, `scripts/manage_users.py`, and legacy `legacy/streamlit_frontend/auth_components.py`. Assumes Firebase Admin is already initialized by its caller — it does not initialize it itself. |
| **`auth/firebase_config.py`** (root) | **Legacy-only.** Streamlit-secrets-or-env Admin SDK init (imports `streamlit`), plus `get_firebase_config()`/`verify_token()` for the old Streamlit app. Only imported by `legacy/streamlit_frontend/auth_components.py`. The current FastAPI backend and CLI do **not** use this module — each initializes Firebase Admin independently (see below). |

**Frontend:** `frontend/src/auth/firebaseConfig.ts` (Web SDK init from `VITE_FIREBASE_*`), `AuthContext.tsx` (`AuthProvider`, `useAuth` — sign-in/sign-out, ID token state, proactive refresh every 55 min, sets the Axios `Authorization` default header), `ProtectedRoute.tsx` (redirects to `/login` if unauthenticated; renders children unconditionally if Firebase isn't configured, so local dev works without credentials). `frontend/src/pages/Login.tsx` — the Sign in / Request access tabbed form.

**CLI:** `scripts/manage_users.py` — admin-only user management (`pending`, `approve`, `reject`, `create`, `list`, `delete`, `update`, `set-claims`, `reset-password`, `delete-request`). Initializes Firebase Admin itself from `backend/config/settings.py` before calling into `auth.user_management`. This is the **only** approval path — there is no admin approval UI in the React app.

## Configuration

Backend credentials come from **`.env`** via `backend/config/settings.py` (pydantic-settings):

```
FIREBASE_PROJECT_ID=
FIREBASE_PRIVATE_KEY=
FIREBASE_CLIENT_EMAIL=
FIREBASE_CLIENT_ID=
FIREBASE_CLIENT_CERT_URL=
```

**Note:** `.env.example` currently lists only the first three of these; `FIREBASE_CLIENT_ID` / `FIREBASE_CLIENT_CERT_URL` are read by `settings.py` but missing from the example file.

Frontend credentials come from **`frontend/.env.local`** (gitignored), copied from `frontend/.env.example` — see the Architecture section above for the exact keys. Get values from Firebase Console → Project Settings → Your Apps → Web App.

**Do not** hardcode any of these values or commit secrets.

### Firebase Admin SDK initialization

There are now **three independent init call sites**, each guarded by the same `firebase_admin._apps` check so re-initialization is a no-op within a process:
1. `backend/auth/firebase_auth.py::_ensure_firebase_initialized()` — used by the FastAPI app.
2. `scripts/manage_users.py::_init_firebase()` — used by the admin CLI.
3. `auth/firebase_config.py` (module-level, at import time) — legacy Streamlit only.

New backend code should initialize via `backend/auth/firebase_auth.py`, not the legacy module.

## Login Flow

1. User opens the React app. If `frontend/.env.local` isn't configured, `LoginPage` renders a "Firebase not configured" warning instead of the form (dev-mode fallback).
2. User submits email + password in `LoginForm` (`frontend/src/pages/Login.tsx`). `AuthContext.signIn()` calls Firebase's `signInWithEmailAndPassword` **directly against Firebase from the browser** — no backend request is involved in authentication itself.
3. On success, Firebase's `onAuthStateChanged` listener in `AuthContext` fires: it fetches the ID token (`getIdToken()`), stores `user`/`token` in React state, and sets `apiClient.defaults.headers.common['Authorization'] = 'Bearer <token>'` for all subsequent API calls.
4. `ProtectedRoute` renders the app if `user` is set; otherwise redirects to `/login`.
5. The token is refreshed proactively every 55 minutes (tokens expire at 60) via `user.getIdToken(true)`.
6. **Protected API calls:** Every protected FastAPI route depends on `verify_firebase_token` (`backend/auth/firebase_auth.py`), which verifies the Bearer token via the Admin SDK and raises `401` on failure or a missing header.

There is no explicit "is this user approved" check at login time in the current code — see Registration and Approval Flow below for why that's still safe.

## Registration and Approval Flow

1. User opens the "Request access" tab (`RegisterForm` in `Login.tsx`). Client-side validation requires an `@addisenergy.com` email. On submit, it `POST`s to `/api/auth/register`.
2. `backend/api/routers/auth.py::register` validates the payload again server-side (Pydantic: domain, role, password length) and calls `auth.user_management.create_pending_user_request()`, which writes a document to Firestore `pending_users` (email, password, display_name, role, status=`pending`). **No Firebase Auth user exists yet.**
3. **Admin:** Uses `scripts/manage_users.py` (`pending` to list, `approve <request_id>` to approve). `approve_user(request_id)` reads the pending document, calls `create_user(email, password, display_name)` (creates the real Firebase Auth account, enforcing `@addisenergy.com` again), then `auth.set_custom_user_claims(uid, {approved: True, role})`, and marks the request `approved`.
4. After approval, the user signs in normally via the React login form (step 2 of Login Flow above). Before approval, sign-in fails with Firebase's own "user not found" error, because the Auth account doesn't exist yet — this is what actually enforces the approval gate now, not a post-login claims check.
5. `role`/`approved` custom claims are set on the Firebase user at approval time but are **not currently read** by `verify_firebase_token` or by any frontend code — they exist for future use (e.g. role-based authorization) but aren't wired into any access-control decision today.

**Security note:** Pending requests store the password in Firestore only until approval. In production, consider a secure alternative (e.g. one-time link to set password) instead of storing the password in a document.

## Token Verification

- **Where:** `backend/auth/firebase_auth.py::verify_firebase_token` (FastAPI dependency, `Depends(verify_firebase_token)` on protected routes).
- **Behavior:** Extracts the `Authorization: Bearer` header, verifies the ID token via the Admin SDK (`check_revoked=False`), and returns a `FirebaseUser(uid, email, display_name)`. Raises `401` if the header is missing or verification fails.
- **Legacy:** `auth/firebase_config.py::verify_token()` still exists for the old Streamlit session-based flow but is not used by the FastAPI backend.

## User Management CLI

Run from project root (or ensure project root is on `PYTHONPATH`):

```bash
python scripts/manage_users.py <command> [args]
```

Commands: `create`, `list`, `delete`, `update`, `pending`, `approve`, `reject`, `delete-request`, `set-claims`, `reset-password`. See `scripts/manage_users.py` for exact arguments. This script initializes Firebase Admin itself from `backend/config/settings.py` — it does not depend on `auth/firebase_config.py`.

## Rules for AI / Maintainers

When editing auth-related code, avoid breaking the following:

1. **Domain restriction** — Registration and login must remain restricted to `@addisenergy.com`. This is enforced independently in three places: `backend/api/schemas/auth.py` (`RegisterRequest` validator), `auth/user_management.py` (`create_user`, `update_user`), and client-side in `RegisterForm`. Do not remove any of these checks.
2. **Approval gate** — Do not create a Firebase Auth account for a pending request outside of `approve_user()`. The gate currently works *because* unapproved emails have no Auth account, not because of a runtime claims check — don't assume a claims check exists elsewhere.
3. **Credentials** — Do not hardcode API keys, private keys, or client emails. Backend reads from `backend/config/settings.py` (`.env`); frontend reads from Vite env vars (`frontend/.env.local`). Document any new keys in this file.
4. **Single initialization per process** — Each entrypoint (FastAPI, CLI, legacy Streamlit) must guard its Firebase Admin init with a `firebase_admin._apps` check before calling `initialize_app`, as all three currently do. New backend code should initialize via `backend/auth/firebase_auth.py`, not `auth/firebase_config.py`.
5. **Token handling** — React holds the ID token in memory (`AuthContext` state) and refreshes it every 55 minutes; it is attached to every API request via the Axios default header. Do not switch to a different token type without updating both `AuthContext.tsx` and `verify_firebase_token`.
6. **Pending users** — Approval must create the user in Firebase Auth and set custom claims; reject/delete should only remove or update the Firestore document, not create Auth users.
7. **Firestore collection** — The pending-users flow depends on the `pending_users` collection and its fields (`email`, `password`, `display_name`, `role`, `status`, `created_at`, `updated_at`, `approved_at`). Changing the schema or collection name should be reflected here and in `auth/user_management.py`.
8. **`role`/`approved` claims are currently informational only** — if you wire them into an access-control decision (e.g. an admin-only endpoint), update this file to describe where that check lives.

## References

- **Shared/live:** `auth/user_management.py` (root)
- **Legacy-only:** `auth/firebase_config.py` (root) — imported only by `legacy/streamlit_frontend/auth_components.py`
- **Backend:** `backend/auth/firebase_auth.py`, `backend/api/routers/auth.py`, `backend/api/schemas/auth.py`
- **Frontend:** `frontend/src/auth/{AuthContext.tsx,firebaseConfig.ts,ProtectedRoute.tsx}`, `frontend/src/pages/Login.tsx`
- **CLI:** `scripts/manage_users.py`
- **Tests:** `tests/test_firebase_config.py`
