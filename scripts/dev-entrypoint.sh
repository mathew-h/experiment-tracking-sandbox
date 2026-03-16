#!/bin/bash
set -e

echo "🚀 Starting Experiment Tracking Development Environment"

# Wait for PostgreSQL
echo "⏳ Waiting for PostgreSQL..."
until pg_isready -h postgres -U experiments_user -d experiments > /dev/null 2>&1; do
  sleep 1
done
echo "✅ PostgreSQL ready"

# Create tables from current models (fresh environment)
# OR run migrations if tables already exist
echo "🗄️  Setting up database schema..."
cd /app
python3 << 'PYTHON_EOF'
from database.database import engine, Base
from database.models import (
    experiments, conditions, results, samples,
    chemicals, analysis, xrd, characterization
)

# Create all tables from current models
Base.metadata.create_all(bind=engine)
print("✅ Database schema created from models")
PYTHON_EOF

# Views will be created during migrations (when implemented)
echo "📊 Database ready with all tables"

echo ""
echo "==========================================="
echo "✨ Development environment ready!"
echo ""
echo "📱 React dev server: http://localhost:5173"
echo "🔌 FastAPI: http://localhost:8000"
echo "📚 Swagger docs: http://localhost:8000/api/docs"
echo "==========================================="
echo ""

# Start both services
echo "Starting FastAPI backend..."
python3 -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload &
FASTAPI_PID=$!

echo "Starting React dev server..."
cd /app/frontend
npm run dev &
REACT_PID=$!

# Keep container running
wait $FASTAPI_PID $REACT_PID
