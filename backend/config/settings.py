from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_master_results_path() -> str:
    return str(
        Path.home()
        / "Addis Energy"
        / "All Company - Addis Energy"
        / "01_R&D"
        / "02_Results"
        / "Master Reactor Sampling Tracker.xlsx"
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://experiments_user:password@localhost:5432/experiments"

    # Firebase — read from FIREBASE_* env vars
    firebase_project_id: str = ""
    firebase_private_key: str = ""
    firebase_client_email: str = ""
    firebase_client_id: str = ""
    firebase_client_cert_url: str = ""

    # Master Results SharePoint path — resolved from the current OS user at startup.
    # Override via MASTER_RESULTS_PATH env var or the master_results_path AppConfig row.
    master_results_path: str = _default_master_results_path()

    # File storage
    sample_photos_dir: str = "sample_photos"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def firebase_cred_dict(self) -> dict:
        return {
            "type": "service_account",
            "project_id": self.firebase_project_id,
            "private_key": self.firebase_private_key.replace("\\n", "\n"),
            "client_email": self.firebase_client_email,
            "client_id": self.firebase_client_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": self.firebase_client_cert_url,
        }


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Override in tests via dependency injection."""
    return Settings()
