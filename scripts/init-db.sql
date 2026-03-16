-- Initial PostgreSQL setup
-- This runs once when the container starts

-- Ensure extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- The database and user are created by POSTGRES_* env vars
-- This script just ensures everything is set up correctly

GRANT ALL PRIVILEGES ON DATABASE experiments TO experiments_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO experiments_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO experiments_user;
