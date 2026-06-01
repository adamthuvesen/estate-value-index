#!/bin/bash
###############################################################################
# Unified Startup Script for Real Estate Price Prediction System
#
# Starts:
#   1. FastAPI inference server (port 8000)
#   2. Next.js web interface (port 3000)
#
# Usage:
#   ./start.sh
#
# Environment Variables:
#   API_PORT - FastAPI port (default: 8000)
#   WEB_PORT - Next.js port (default: 3000)
#   PYTHON - Python executable path (default: auto-detect)
###############################################################################

set -e  # Exit on error

# Configuration
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
API_HOST="0.0.0.0"
MAX_STARTUP_WAIT=30  # seconds

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# PID tracking
API_PID=""
WEB_PID=""

# Cleanup function
cleanup() {
    log_info "Shutting down services..."
    
    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
        log_info "Stopping Next.js (PID: $WEB_PID)..."
        kill -TERM "$WEB_PID" 2>/dev/null || true
        wait "$WEB_PID" 2>/dev/null || true
    fi
    
    if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
        log_info "Stopping FastAPI (PID: $API_PID)..."
        kill -TERM "$API_PID" 2>/dev/null || true
        wait "$API_PID" 2>/dev/null || true
    fi
    
    log_success "All services stopped"
    exit 0
}

# Register cleanup on signals
trap cleanup SIGINT SIGTERM EXIT

# Find Python executable
find_python() {
    # Try .venv first
    if [ -f ".venv/bin/python" ]; then
        echo ".venv/bin/python"
        return 0
    fi
    
    # Try VIRTUAL_ENV
    if [ -n "$VIRTUAL_ENV" ] && [ -f "$VIRTUAL_ENV/bin/python" ]; then
        echo "$VIRTUAL_ENV/bin/python"
        return 0
    fi
    
    # Try environment variable
    if [ -n "$PYTHON" ] && command -v "$PYTHON" >/dev/null 2>&1; then
        echo "$PYTHON"
        return 0
    fi
    
    # Try common names
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            echo "$cmd"
            return 0
        fi
    done
    
    log_error "Python not found. Please activate virtual environment or set PYTHON variable."
    exit 1
}

# Check if port is available
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 1
    fi
    return 0
}

# Wait for API to be healthy
wait_for_api() {
    local max_wait=$1
    local elapsed=0
    
    log_info "Waiting for FastAPI to be ready (timeout: ${max_wait}s)..."
    
    while [ $elapsed -lt $max_wait ]; do
        if curl -sf "http://localhost:${API_PORT}/health" >/dev/null 2>&1; then
            log_success "FastAPI is ready!"
            return 0
        fi
        
        sleep 1
        elapsed=$((elapsed + 1))
        
        # Show progress every 5 seconds
        if [ $((elapsed % 5)) -eq 0 ]; then
            log_info "Still waiting... (${elapsed}s / ${max_wait}s)"
        fi
    done
    
    log_error "FastAPI failed to become ready within ${max_wait}s"
    return 1
}

###############################################################################
# Main startup sequence
###############################################################################

log_info "Starting Real Estate Price Prediction System..."
echo ""

# Find Python
PYTHON_CMD=$(find_python)
log_info "Using Python: $PYTHON_CMD"

# Verify we're in the project root
if [ ! -f "api_server.py" ]; then
    log_error "api_server.py not found. Please run from project root."
    exit 1
fi

if [ ! -d "web" ]; then
    log_error "web/ directory not found. Please run from project root."
    exit 1
fi

# Check ports
log_info "Checking port availability..."

if ! check_port "$API_PORT"; then
    log_error "Port $API_PORT is already in use (FastAPI)"
    exit 1
fi

if ! check_port "$WEB_PORT"; then
    log_error "Port $WEB_PORT is already in use (Next.js)"
    exit 1
fi

log_success "Ports $API_PORT and $WEB_PORT are available"
echo ""

###############################################################################
# Start FastAPI Server
###############################################################################

log_info "Starting FastAPI inference server on port $API_PORT..."

$PYTHON_CMD -m uvicorn api_server:app \
    --host "$API_HOST" \
    --port "$API_PORT" \
    --log-level info \
    > logs/api_server.log 2>&1 &

API_PID=$!

# Verify process started
sleep 1
if ! kill -0 "$API_PID" 2>/dev/null; then
    log_error "FastAPI failed to start. Check logs/api_server.log"
    exit 1
fi

log_success "FastAPI started (PID: $API_PID)"

# Wait for API to be healthy
if ! wait_for_api "$MAX_STARTUP_WAIT"; then
    log_error "Check logs/api_server.log for details"
    exit 1
fi

echo ""

###############################################################################
# Start Next.js Server
###############################################################################

log_info "Starting Next.js web server on port $WEB_PORT..."

cd web

# Set environment variable for API URL
export NEXT_PUBLIC_API_URL="http://localhost:${API_PORT}"
export PREDICTION_API_URL="http://localhost:${API_PORT}"

npm run dev -- -p "$WEB_PORT" &
WEB_PID=$!

cd ..

# Verify process started
sleep 2
if ! kill -0 "$WEB_PID" 2>/dev/null; then
    log_error "Next.js failed to start"
    exit 1
fi

log_success "Next.js started (PID: $WEB_PID)"
echo ""

###############################################################################
# Ready
###############################################################################

log_success "All services are running!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🚀 Real Estate Price Prediction System"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  📊 FastAPI Server:  http://localhost:${API_PORT}"
echo "  📖 API Docs:        http://localhost:${API_PORT}/docs"
echo "  🌐 Web Interface:   http://localhost:${WEB_PORT}"
echo ""
echo "  Logs:"
echo "    API Server:       logs/api_server.log"
echo "    Web Server:       (stdout)"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Wait for Web process (foreground)
wait "$WEB_PID"

