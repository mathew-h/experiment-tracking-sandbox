from backend.config.settings import Settings


def test_settings_loads_database_url():
    s = Settings(database_url="postgresql://u:p@localhost/test")
    assert s.database_url == "postgresql://u:p@localhost/test"


def test_settings_cors_origins_list():
    s = Settings(cors_origins="http://localhost:5173,http://localhost:8000")
    assert "http://localhost:5173" in s.cors_origins_list
    assert "http://localhost:8000" in s.cors_origins_list
