"""AppConfig — runtime-mutable key-value store for application settings."""
from __future__ import annotations

from sqlalchemy import Column, String, Text, DateTime, func

from ..database import Base


class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
