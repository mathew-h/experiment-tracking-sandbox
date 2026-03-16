import os
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import urlparse

# Add parent directory to path for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database_backup import create_archived_backup, update_public_db_copy, cleanup_old_backups
from utils.scheduler import setup_backup_scheduler, shutdown_scheduler, create_backup_now, create_public_copy_now


@pytest.fixture
def temp_dirs():
    """Create temporary directories for test backups and public copies."""
    temp_backup_dir = tempfile.mkdtemp()
    temp_public_dir = tempfile.mkdtemp()
    
    # Create a test database
    test_db_path = os.path.join(temp_backup_dir, "test_db.db")
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO test (name) VALUES ('test_data')")
    conn.commit()
    conn.close()
    
    yield {
        'backup_dir': temp_backup_dir,
        'public_dir': temp_public_dir,
        'db_path': test_db_path
    }
    
    # Cleanup
    shutil.rmtree(temp_backup_dir, ignore_errors=True)
    shutil.rmtree(temp_public_dir, ignore_errors=True)

@pytest.fixture
def create_test_backups():
    """Create test backup files with different timestamps."""
    def _create_backups(backup_dir, count=10):
        # Create backup files with timestamps spread over the last 'count' days
        now = datetime.now()
        backup_files = []
        for i in range(count):
            timestamp = (now - timedelta(days=i)).strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"experiments_backup_{timestamp}.db")
            # Create empty file
            with open(backup_file, "w") as f:
                f.write("test")
            backup_files.append(backup_file)
        
        return sorted(Path(backup_dir).glob("experiments_backup_*.db"), 
                      key=lambda x: x.stat().st_mtime,
                      reverse=True)
    return _create_backups

@patch("utils.database_backup.DATABASE_URL", "sqlite:///test_db.db")
@patch("utils.database_backup.get_storage_config")
def test_create_archived_backup(mock_get_config, temp_dirs):
    """Test that create_archived_backup creates a backup file correctly."""
    # Mock the storage config
    mock_get_config.return_value = {
        "backup_directory": temp_dirs['backup_dir']
    }
    
    # Mock the database path to point to our test database
    with patch("utils.database_backup.urlparse") as mock_urlparse:
        mock_urlparse.return_value = MagicMock(
            scheme="sqlite",
            path=temp_dirs['db_path']
        )
        
        # Call the function
        backup_path = create_archived_backup()
        
        # Verify a backup was created
        assert backup_path is not None
        assert os.path.exists(backup_path)
        assert backup_path.startswith(temp_dirs['backup_dir'])
        assert f"{Path(temp_dirs['db_path']).stem}_backup_" in backup_path
        assert backup_path.endswith(".db")
        
        # Verify the backup is a valid SQLite database with our test data
        conn = sqlite3.connect(backup_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM test")
        result = cursor.fetchone()
        assert result[0] == "test_data"
        conn.close()

@patch("utils.database_backup.DATABASE_URL", "sqlite:///test_db.db")
@patch("os.environ")
def test_update_public_db_copy(mock_environ, temp_dirs):
    """Test that update_public_db_copy creates a public copy correctly."""
    # Mock environment variables
    mock_environ.get.return_value = temp_dirs['public_dir']
    
    # Mock the database path to point to our test database
    with patch("utils.database_backup.urlparse") as mock_urlparse:
        mock_urlparse.return_value = MagicMock(
            scheme="sqlite",
            path=temp_dirs['db_path']
        )
        
        # Use a simplified approach without mocking Path.name
        # Call the function with direct mocking of the original path
        public_path = update_public_db_copy()
        
        # Verify a public copy was created
        assert public_path is not None
        assert os.path.exists(public_path)
        assert public_path.startswith(temp_dirs['public_dir'])
        
        # Extract the filename from the path and verify it
        filename = os.path.basename(public_path)
        assert filename == os.path.basename(temp_dirs['db_path'])

@patch("utils.database_backup.get_storage_config")
def test_cleanup_old_backups(mock_get_config, temp_dirs, create_test_backups):
    """Test that cleanup_old_backups removes old backups correctly."""
    # Mock the storage config
    mock_get_config.return_value = {
        "backup_directory": temp_dirs['backup_dir']
    }
    
    # Create test backup files
    backup_files = create_test_backups(temp_dirs['backup_dir'], count=10)
    assert len(backup_files) == 10
    
    # Call the function to keep only 5 backups
    cleanup_old_backups(keep_last_n=5)
    
    # Verify only 5 backups remain
    remaining_files = list(Path(temp_dirs['backup_dir']).glob("*_backup_*.db"))
    assert len(remaining_files) == 5
    
    # Verify the newest backups were kept
    for i in range(5):
        assert os.path.exists(str(backup_files[i]))
        
    # Verify the oldest backups were removed
    for i in range(5, 10):
        assert not os.path.exists(str(backup_files[i]))

@patch("utils.scheduler.BackgroundScheduler")
def test_setup_backup_scheduler(mock_scheduler_class):
    """Test that the backup scheduler is set up correctly."""
    # Mock the scheduler
    mock_scheduler = MagicMock()
    mock_scheduler_class.return_value = mock_scheduler
    mock_scheduler.running = False
    
    # Call the function
    result = setup_backup_scheduler(
        backup_interval_hours=24,
        cleanup_interval_days=7,
        public_copy_interval_hours=6,
        keep_backups=3
    )
    
    # Verify the scheduler was started
    assert result == mock_scheduler
    mock_scheduler.start.assert_called_once()
    
    # Verify all jobs were added
    assert mock_scheduler.add_job.call_count == 3
    
    # Verify each job was added with correct parameters
    job_ids = []
    for call in mock_scheduler.add_job.call_args_list:
        args, kwargs = call
        job_ids.append(kwargs.get('id'))
        assert 'func' in kwargs
        assert 'trigger' in kwargs
        assert 'replace_existing' in kwargs
        
    assert 'database_backup' in job_ids
    assert 'backup_cleanup' in job_ids
    assert 'public_database_copy' in job_ids

@patch("utils.scheduler.scheduler")
def test_shutdown_scheduler(mock_scheduler):
    """Test that the scheduler is shut down correctly."""
    # Mock the scheduler
    mock_scheduler.running = True
    
    # Call the function
    shutdown_scheduler()
    
    # Verify the scheduler was shut down
    mock_scheduler.shutdown.assert_called_once()

@patch("utils.scheduler.create_archived_backup")
def test_create_backup_now(mock_backup_func):
    """Test that create_backup_now calls create_archived_backup correctly."""
    # Mock the backup function
    mock_backup_func.return_value = "/path/to/backup.db"
    
    # Call the function
    result = create_backup_now()
    
    # Verify create_archived_backup was called
    mock_backup_func.assert_called_once()
    assert result == "/path/to/backup.db"

@patch("utils.scheduler.update_public_db_copy")
def test_create_public_copy_now(mock_public_copy_func):
    """Test that create_public_copy_now calls update_public_db_copy correctly."""
    # Mock the copy function
    mock_public_copy_func.return_value = "/path/to/public.db"
    
    # Call the function
    result = create_public_copy_now()
    
    # Verify update_public_db_copy was called
    mock_public_copy_func.assert_called_once()
    assert result == "/path/to/public.db"

@patch("utils.database_backup.DATABASE_URL", "postgres://localhost:5432/experiments")
@patch("utils.database_backup.get_storage_config")
@patch("utils.database_backup.logger")
def test_create_archived_backup_non_sqlite(mock_logger, mock_get_config, temp_dirs):
    """Test that create_archived_backup handles non-SQLite databases correctly."""
    # Mock the storage config
    mock_get_config.return_value = {
        "backup_directory": temp_dirs['backup_dir']
    }
    
    # Mock the database path
    with patch("utils.database_backup.urlparse") as mock_urlparse:
        mock_urlparse.return_value = MagicMock(
            scheme="postgres",
            path="/experiments"
        )
        
        # Call the function
        result = create_archived_backup()
        
        # Verify warning was logged and function returned None
        assert result is None
        mock_logger.warning.assert_called()

@patch("utils.database_backup.DATABASE_URL", "sqlite:///nonexistent.db")
@patch("utils.database_backup.get_storage_config")
def test_create_archived_backup_file_not_found(mock_get_config, temp_dirs):
    """Test that create_archived_backup handles missing database files correctly."""
    # Mock the storage config
    mock_get_config.return_value = {
        "backup_directory": temp_dirs['backup_dir']
    }
    
    # Mock the database path
    with patch("utils.database_backup.urlparse") as mock_urlparse:
        mock_urlparse.return_value = MagicMock(
            scheme="sqlite",
            path="/nonexistent.db"
        )
        
        # Call the function and expect a FileNotFoundError
        with pytest.raises(FileNotFoundError):
            create_archived_backup()

@patch("os.environ")
def test_update_public_db_copy_no_env_var(mock_environ):
    """Test that update_public_db_copy handles missing environment variable correctly."""
    mock_environ.get.return_value = None
    
    result = update_public_db_copy()
    assert result is None

@patch("utils.database_backup.shutil.copy2")
def test_create_archived_backup_exception(mock_copy, mock_get_config, temp_dirs):
    """Test that create_archived_backup handles exceptions during copy."""
    # Mock the storage config
    mock_get_config.return_value = {
        "backup_directory": temp_dirs['backup_dir']
    }
    
    # Mock the database path
    with patch("utils.database_backup.urlparse") as mock_urlparse:
        mock_urlparse.return_value = MagicMock(
            scheme="sqlite",
            path="/nonexistent.db"
        )
        
        # Expect a generic exception because the original function raises it
        with pytest.raises(Exception):
            create_archived_backup()

@patch("utils.database_backup.shutil.copy2")
def test_update_public_db_copy_exception(mock_copy, mock_environ, temp_dirs):
    """Test that update_public_db_copy handles exceptions during copy."""
    # Mock the environment variables
    mock_environ.get.return_value = None
    
    # Call the function
    result = update_public_db_copy()
    assert result is None
