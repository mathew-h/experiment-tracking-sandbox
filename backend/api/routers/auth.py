from __future__ import annotations
import structlog
from fastapi import APIRouter, HTTPException, status
from backend.api.schemas.auth import RegisterRequest, RegisterResponse
from backend.auth.firebase_auth import _ensure_firebase_initialized

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(payload: RegisterRequest) -> RegisterResponse:
    """Submit an account request. Writes a pending entry to Firestore for admin approval."""
    _ensure_firebase_initialized()
    try:
        from auth.user_management import create_pending_user_request
    except ImportError as exc:
        log.error("user_management_import_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service unavailable",
        ) from exc

    try:
        create_pending_user_request(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        log.error("register_request_failed", email=payload.email, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit registration request",
        ) from exc

    log.info("register_request_submitted", email=payload.email, role=payload.role)
    return RegisterResponse(
        message="Request submitted — your lab admin will approve your account before you can sign in."
    )
