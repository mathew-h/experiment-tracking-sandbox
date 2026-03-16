import os
import sys
from sqlalchemy import text

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import DATABASE_URL

# Use relative import for database module
from .database import engine, init_db, SessionLocal

def confirm_reset():
    """Ask for confirmation before resetting the database."""
    print("\n⚠️  WARNING: This will drop all existing tables and data!")
    print(f"Database URL: {DATABASE_URL}")
    confirmation = input("\nAre you sure you want to reset the database? (yes/no): ")
    return confirmation.lower() == 'yes'

def check_database_connection():
    """Test the database connection."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"❌ Error connecting to database: {str(e)}")
        return False

def reset_database():
    """Drop all tables and recreate them."""
    try:
        # Check if using SQLite
        if DATABASE_URL.startswith('sqlite'):
            # For SQLite, just drop all tables using metadata
            from .models import Base
            Base.metadata.drop_all(bind=engine)
            print("✅ Successfully dropped all tables from SQLite")
        else:
            # For PostgreSQL, drop and recreate the schema
            with engine.connect() as conn:
                conn.execute(text("DROP SCHEMA public CASCADE"))
                conn.execute(text("CREATE SCHEMA public"))
                conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
                conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
                conn.commit()
            print("✅ Successfully dropped all tables from PostgreSQL")
    except Exception as e:
        print(f"❌ Error dropping tables: {str(e)}")
        sys.exit(1)

def create_tables():
    """Create all tables defined in the models."""
    try:
        init_db()
        print("✅ Successfully created all tables")
    except Exception as e:
        print(f"❌ Error creating tables: {str(e)}")
        sys.exit(1)

def main():
    print("\n=== Database Initialization Script ===\n")
    
    # Check database connection
    if not check_database_connection():
        print("❌ Failed to connect to database. Please check your connection settings.")
        sys.exit(1)
    
    # Ask if user wants to reset the database
    if confirm_reset():
        reset_database()
    else:
        print("\nOperation cancelled.")
        sys.exit(0)
    
    # Create tables
    create_tables()
    
    print("\n✨ Database initialization complete!")
    print("You can now run the application using: streamlit run app.py\n")

if __name__ == "__main__":
    main() 