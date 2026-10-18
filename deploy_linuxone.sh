#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
#  NourishNet AI — LinuxONE Deployment Script
#  IBM Z Datathon 2026 | Track 1: Real-Time AI for Critical Decisions
# ═══════════════════════════════════════════════════════════════════════════

set -e

echo "╔════════════════════════════════════════════════════════╗"
echo "║        🍽️  NourishNet AI — LinuxONE Deployer          ║"
echo "║        IBM Z Datathon 2026                             ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# ── Platform verification ─────────────────────────────────────────────────
echo "📋 Platform Info:"
echo "   Architecture : $(uname -m)"
echo "   OS           : $(uname -s) $(uname -r)"
echo "   Python       : $(python3 --version 2>/dev/null || echo 'Not found')"
echo ""

if [ "$(uname -m)" = "s390x" ]; then
    echo "✅ Running on IBM LinuxONE (s390x) — confirmed!"
else
    echo "⚠️  Not running on s390x (current: $(uname -m)). Proceeding anyway..."
fi
echo ""

# ── Python check ──────────────────────────────────────────────────────────
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "❌ Python not found. Please install Python 3.9+."
    exit 1
fi

echo "🐍 Using: $PYTHON ($($PYTHON --version))"
echo ""

# ── s390x System Packages Check ───────────────────────────────────────────
if [ "$(uname -m)" = "s390x" ]; then
    if ! $PYTHON -c "import scipy, numpy, sklearn, pandas" &>/dev/null; then
        echo "📦 Installing Ubuntu pre-compiled scientific packages for s390x..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3-scipy python3-numpy python3-pandas python3-sklearn python3-venv libopenblas-dev
        echo "✅ System scientific packages installed"
        echo ""
    fi
fi

# ── Virtual environment ───────────────────────────────────────────────────
VENV_DIR=".venv"

# If venv exists but cannot import scipy, recreate with system-site-packages
if [ -d "$VENV_DIR" ]; then
    if ! "$VENV_DIR/bin/python3" -c "import scipy" &>/dev/null; then
        echo "🔄 Recreating virtual environment with system packages..."
        rm -rf "$VENV_DIR"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment with system site packages..."
    $PYTHON -m venv --system-site-packages "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "✅ Virtual environment activated"
echo ""

# ── Install dependencies ─────────────────────────────────────────────────
echo "📥 Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# ── Environment setup ────────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env from template"
fi

# ── Build React Frontend (if node available and dist missing) ────────────
if [ ! -d "frontend/dist" ] && command -v npm &>/dev/null; then
    echo "🔨 Building React production bundle..."
    cd frontend && npm install && npm run build && cd ..
fi

# ── Stop existing processes ──────────────────────────────────────────────
echo "🛑 Stopping any existing NourishNet processes..."
pkill -f "uvicorn backend.main:app" 2>/dev/null || true
sleep 1

# ── Start unified server ─────────────────────────────────────────────────
echo "🚀 Starting unified FastAPI + React server on port 8000..."
nohup python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
SERVER_PID=$!
echo "   PID: $SERVER_PID"
sleep 3

# Verify server is running
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✅ Server is running!"
    curl -s http://localhost:8000/api/health | python3 -m json.tool 2>/dev/null || true
else
    echo "⚠️  Server may still be starting... check server.log"
fi
echo ""

# ── Print access info ────────────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo "╔════════════════════════════════════════════════════════╗"
echo "║              ✅ NourishNet AI is LIVE!                 ║"
echo "╠════════════════════════════════════════════════════════╣"
echo "║  🌐 Web Application: http://$IP:8000                   ║"
echo "║  📖 API Docs       : http://$IP:8000/docs              ║"
echo "║                                                        ║"
echo "║  📋 Server Logs    : tail -f server.log                ║"
echo "╠════════════════════════════════════════════════════════╣"
echo "║  🖥️  Platform: $(uname -m)                             ║"
echo "║  🐍 Python  : $($PYTHON --version)                     ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "🎉 Deployment complete! NourishNet AI is ready for the judges."
