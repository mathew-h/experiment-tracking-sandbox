from __future__ import annotations
from typing import Optional
import structlog
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth_module
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from backend.config.settings import get_settings

log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)
_firebase_initialized = False


def _ensure_firebase_initialized() -> None:
    """Initialize Firebase Admin SDK once from settings. No-op if already done."""
    global _firebase_initialized
    if _firebase_initialized or firebase_admin._apps:
        _firebase_initialized = True
        return
    settings = get_settings()
    if not settings.firebase_project_id:
        log.warning("firebase_project_id_not_set_skipping_init")
        return
    cred = credentials.Certificate(settings.firebase_cred_dict)
    firebase_admin.initialize_app(cred)
    _firebase_initialized = True
    log.info("firebase_admin_initialized", project=settings.firebase_project_id)


def _verify_id_token(token: str) -> dict:
    """Thin wrapper around firebase_auth.verify_id_token — patched in tests."""
    _ensure_firebase_initialized()
    return firebase_auth_module.verify_id_token(token, check_revoked=False)


class FirebaseUser(BaseModel):
    uid: str
    email: str
    display_name: str = ""


def _decode_token(token: str) -> FirebaseUser:
    """Verify token and return FirebaseUser. Raises HTTP 401 on failure."""
    try:
        decoded = _verify_id_token(token)
    except Exception as exc:
        log.warning("token_verification_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    return FirebaseUser(
        uid=decoded.get("uid", decoded.get("user_id", "")),
        email=decoded.get("email", ""),
        display_name=decoded.get("name", ""),
    )


def verify_firebase_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> FirebaseUser:
    """FastAPI dependency: extract Bearer token and return authenticated user."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    return _decode_token(credentials.credentials)
