#!/bin/bash
# Quick start script for Derivatives Protocol Backend

set -e

echo "🚀 Derivatives Protocol Backend - Quick Start"
echo "=============================================="
echo ""

# Check Python version
echo "✓ Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "  Python version: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "✓ Creating virtual environment..."
    python3 -m venv venv
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "✓ Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "✓ Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Setup .env file
if [ ! -f ".env" ]; then
    echo "✓ Creating .env file from template..."
    cp .env.example .env
    echo "  ⚠️  Please edit .env file with your configuration"
    echo "  Required: DATABASE_URL, RPC_URL, CONTRACT_ADDRESS"
else
    echo "✓ .env file already exists"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Start PostgreSQL database (or use docker-compose)"
echo "3. Run: python scripts/seed_db.py (to create sample markets)"
echo "4. Run: python -m app.main (to start the server)"
echo ""
echo "Or use Docker Compose:"
echo "  docker-compose up -d"
echo ""
echo "API will be available at: http://localhost:8000"
echo "API docs at: http://localhost:8000/docs"
