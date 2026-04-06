from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_master_results_path() -> str:
    """Resolve the SharePoint-synced master tracker path for the current machine.

    When the server runs as a Windows service (SYSTEM account), Path.home()
    resolves to the service profile, not the logged-in user's folder.
    Scan C:\\Users\\ for any user directory that actually contains the file so
    the default works on any machine without manual configuration.
    """
    import os  # noqa: PLC0415

    relative = (
        Path("Addis Energy")
        / "All Company - Addis Energy"
        / "01_R&D"
        / "02_Results"
        / "Master Reactor Sampling Tracker.xlsx"
    )

    # 1. USERPROFILE env var — set by Windows for the interactive session user
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidate = Path(userprofile) / relative
        if candidate.exists():
            return str(candidate)

    # 2. Scan C:\Users\ for any user who has the file (handles service-account context)
    users_dir = Path(r"C:\Users")
    if users_dir.exists():
        for user_dir in sorted(users_dir.iterdir()):
            if user_dir.is_dir():
                candidate = user_dir / relative
                if candidate.exists():
                    return str(candidate)

    # 3. Fall back to USERPROFILE / Path.home() even if the file doesn't exist yet
    if userprofile:
        return str(Path(userprofile) / relative)
    return str(Path.home() / relative)


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

    # Notion sync — reactor dashboard
    notion_token: str = ""
    notion_database_id: str = ""
    notion_data_source_id: str = ""
    notion_sync_hour: int = 6  # Hour of day (24h) in America/New_York to run daily sync

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
