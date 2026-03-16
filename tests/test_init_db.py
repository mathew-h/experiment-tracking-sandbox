import os
import sys
import sqlite3
from sqlalchemy import inspect

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE_URL
from database import engine, init_db

def check_sqlite_tables():
    """Check if tables exist in SQLite database."""
    if not DATABASE_URL.startswith('sqlite'):
        print("Not using SQLite, skipping this check")
        return

    # Extract the database path from the URL
    db_path = DATABASE_URL.replace('sqlite:///', '')
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found at {db_path}")
        return
    
    print(f"✅ Database file exists at {db_path}")
    
    # Connect to the database and list tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    conn.close()
    
    if not tables:
        print("❌ No tables found in database")
    else:
        print(f"✅ Found {len(tables)} tables in database:")
        for table in tables:
            print(f"  - {table[0]}")

def check_sqlalchemy_tables():
    """Check if tables exist using SQLAlchemy."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    if not table_names:
        print("❌ No tables found through SQLAlchemy inspection")
    else:
        print(f"✅ Found {len(table_names)} tables through SQLAlchemy:")
        for table in table_names:
            print(f"  - {table}")
            columns = inspector.get_columns(table)
            print(f"     Columns: {len(columns)}")

def main():
    print("\n=== Testing Database Initialization ===\n")
    print(f"Using database: {DATABASE_URL}")
    
    # Initialize the database
    try:
        init_db()
        print("✅ Database initialization successful")
    except Exception as e:
        print(f"❌ Error initializing database: {str(e)}")
        sys.exit(1)
    
    # Check for tables
    check_sqlite_tables()
    check_sqlalchemy_tables()
    
    print("\n✨ Database test complete!")

if __name__ == "__main__":
    main() 