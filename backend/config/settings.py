from __future__ import annotations
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # File storage
    sample_photos_dir: str = "sample_photos"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    # ActLabs sample ID fuzzy matching threshold (0.0–1.0, default 0.90)
    actlabs_similarity_threshold: float = Field(default=0.90, ge=0.0, le=1.0)

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
