from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

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


def reset_postgres_sequences() -> None:
    """
    Reset all PostgreSQL serial sequences to be consistent with the current MAX(id).

    After a SQLite→PostgreSQL migration (or any bulk import that inserts rows with
    explicit IDs), the sequences are left at their initial values (1) while the table
    data already has higher IDs.  Every subsequent INSERT then collides with an
    existing primary key.

    Safe to call on every startup — it is a no-op when sequences are already correct.
    Only runs when the DATABASE_URL points to PostgreSQL.
    """
    if "postgresql" not in DATABASE_URL:
        return

    insp = inspect(engine)
    tables = insp.get_table_names()

    reset_count = 0
    with engine.connect() as conn:
        for table in tables:
            cols = {c["name"] for c in insp.get_columns(table)}
            if "id" not in cols:
                continue
            try:
                conn.execute(text(
                    f"SELECT setval("
                    f"  pg_get_serial_sequence('{table}', 'id'),"
                    f"  COALESCE((SELECT MAX(id) FROM \"{table}\"), 1)"
                    f")"
                ))
                reset_count += 1
            except Exception:
                # Table may use a UUID PK or have no sequence — skip silently.
                pass
        conn.commit()

    logger.info("reset_postgres_sequences: reset %d sequence(s)", reset_count) 