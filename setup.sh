#!/bin/bash
# Initial setup script for experiment_tracking_sandbox

set -e

echo "🚀 Setting up Experiment Tracking Sandbox"
echo "=========================================="

REPO_ROOT=$(pwd)

# Check if this is the right directory
if [ ! -f "docker-compose.yml" ]; then
  echo "❌ Error: docker-compose.yml not found. Run this script from the repo root."
  exit 1
fi

echo ""
echo "📋 Initialization Checklist:"
echo ""

# 1. Create necessary directories
echo "  1️⃣  Creating directories..."
mkdir -p backend/api/{routers,schemas}
mkdir -p backend/auth backend/services/bulk_uploads
mkdir -p database/models
mkdir -p frontend/src/{api,components,pages,layouts,auth,styles}
mkdir -p alembic/versions
mkdir -p tests/{api,models,services,fixtures}
mkdir -p docs/{api,frontend,user_guide,developer,deployment,sample_data}
mkdir -p scripts logs data
echo "     ✅ Done"

# 2. Copy environment file
echo "  2️⃣  Setting up environment..."
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "     ✅ Created .env (update with your values)"
else
  echo "     ✅ .env already exists"
fi

# 3. Check Docker
echo "  3️⃣  Checking Docker..."
if ! command -v docker &> /dev/null; then
  echo "     ❌ Docker not found. Install Docker Desktop before proceeding."
  exit 1
fi
if ! command -v docker-compose &> /dev/null; then
  echo "     ❌ docker-compose not found. Install Docker Desktop before proceeding."
  exit 1
fi
echo "     ✅ Docker ready"

# 4. Make scripts executable
echo "  4️⃣  Setting script permissions..."
chmod +x scripts/dev-entrypoint.sh
chmod +x scripts/migrate-sqlite-to-postgres.py
chmod +x setup.sh
echo "     ✅ Done"

# 5. Verify experiments.db exists
echo "  5️⃣  Verifying sample data..."
if [ ! -f "docs/sample_data/experiments.db" ]; then
  echo "     ⚠️  Warning: docs/sample_data/experiments.db not found"
  echo "     This is needed for Milestone 1 migration testing."
else
  DB_SIZE=$(du -h docs/sample_data/experiments.db | cut -f1)
  echo "     ✅ Found experiments.db ($DB_SIZE)"
fi

echo ""
echo "=========================================="
echo "✨ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Copy project files (database/, backend/, frontend/, alembic/)"
echo "  2. Copy requirements.txt and frontend/package.json"
echo "  3. Run: docker-compose up --build"
echo ""
echo "📚 Documentation:"
echo "  - Dev setup: README_DEV_SETUP.md"
echo "  - Schema reference: .claude/MEMORY.md"
echo "  - Schema checklist: .claude/rules/schema-checklist.md"
echo ""
