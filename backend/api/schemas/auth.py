from __future__ import annotations
from pydantic import BaseModel, field_validator


class RegisterRequest(BaseModel):
    """Access request. No password: the user sets one via the link sent at approval.

    Unknown fields (e.g. ``password`` from a stale cached frontend) are ignored.
    """

    email: str
    display_name: str
    role: str

    @field_validator("email")
    @classmethod
    def must_be_addisenergy(cls, v: str) -> str:
        if not v.lower().endswith("@addisenergy.com"):
            raise ValueError("Email must be an @addisenergy.com address")
        return v.lower()

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        allowed = {"researcher", "admin"}
        if v.lower() not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(sorted(allowed))}")
        return v.lower()

    @field_validator("display_name")
    @classmethod
    def display_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Display name is required")
        return v.strip()


class RegisterResponse(BaseModel):
    message: str
