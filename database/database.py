from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://experiments_user:experiments_dev_password@postgres:5432/experiments"
)

# PostgreSQL connection args
DB_CONNECT_ARGS = {} if "postgresql" in DATABASE_URL else {"check_same_thread": False}

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL, connect_args=DB_CONNECT_ARGS)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base
Base = declarative_base()

# Import to register listeners. This must be done after Base is defined to avoid circular imports.
from . import event_listeners

def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 