#!/bin/bash
# Server startup script for SuperMemory
# This script starts the application with network access enabled

# NOTE: Do NOT use "set -e" here - it causes issues with signal handling
# When Ctrl+C interrupts sleep, it returns non-zero and would exit the script

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================="
echo "Starting SuperMemory Server"
echo -e "==========================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "app.py" ] || [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ Error: Not in SuperMemory directory${NC}"
    echo "Please run this script from the SuperMemory root directory"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
    echo ""
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo ""

# Check if dependencies are installed
echo -e "${YELLOW}Checking dependencies...${NC}"
if ! python -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}Dependencies not installed. Installing...${NC}"
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Dependencies already installed${NC}"
fi
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found${NC}"
    if [ -f ".env.example" ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
        echo -e "${GREEN}✓ Created .env file${NC}"
        echo ""
        echo -e "${RED}IMPORTANT: Edit .env and set your configuration!${NC}"
        echo "Required settings:"
        echo "  - GEMINI_API_KEY: Your Gemini API key"
        echo "  - HOST=0.0.0.0 (for network access)"
        echo "  - PORT=5000 (or your preferred port)"
        echo "  - DEBUG=false (for production)"
        echo ""
        read -p "Do you want to edit .env now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        else
            echo "Remember to edit .env before the app will work properly!"
        fi
    else
        echo -e "${RED}❌ Error: .env.example not found${NC}"
        exit 1
    fi
fi

# Load environment variables safely using set -a
# set -a: automatically export all variables that are set
# This is safer than 'export $(...)' which can execute arbitrary code
set -a
source .env
set +a

# Check if GEMINI_API_KEY is set
if [ -z "$GEMINI_API_KEY" ] || [ "$GEMINI_API_KEY" = "your_gemini_api_key_here" ]; then
    echo -e "${YELLOW}⚠️  Warning: GEMINI_API_KEY not configured${NC}"
    echo "The app will start but video annotation will not work without a valid API key."
    echo "Please edit .env and set your GEMINI_API_KEY"
    echo ""
fi

# Set default values if not specified in .env
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-5000}
DEBUG=${DEBUG:-false}

# Display configuration
echo -e "${BLUE}Configuration:${NC}"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  Debug: ${DEBUG}"
echo ""

# Get server hostname and IP
HOSTNAME=$(hostname -f 2>/dev/null || hostname)
IPS=$(hostname -I 2>/dev/null || echo "Unable to determine IP")

echo -e "${BLUE}Server Information:${NC}"
echo "  Hostname: ${HOSTNAME}"
echo "  IP Addresses: ${IPS}"
echo ""

# Display access URLs
echo -e "${GREEN}=========================================="
echo "Starting application..."
echo -e "==========================================${NC}"
echo ""
echo -e "${GREEN}Access URLs:${NC}"

if [ "$HOST" = "0.0.0.0" ]; then
    echo "  Local:   http://localhost:${PORT}"
    echo "  Network: http://${HOSTNAME}:${PORT}"
    for ip in $IPS; do
        echo "           http://${ip}:${PORT}"
    done
else
    echo "  Local only: http://${HOST}:${PORT}"
    echo ""
    echo -e "${YELLOW}⚠️  Note: HOST is set to ${HOST}${NC}"
    echo "  To enable network access, set HOST=0.0.0.0 in .env"
fi

echo ""
echo -e "${BLUE}Press Ctrl+C to stop the server${NC}"
echo ""

# Start the application
# Global variable to control the restart loop
SHOULD_RESTART=0
APP_PID=""

# Function to kill the server process and its children
kill_server() {
    if [ -n "$APP_PID" ]; then
        # Kill the entire process group
        kill -- -$APP_PID 2>/dev/null || true
        # Also try killing directly
        kill $APP_PID 2>/dev/null || true
        # Wait for cleanup
        wait $APP_PID 2>/dev/null || true
        APP_PID=""
    fi
    # Also kill anything on port 5000 to be safe
    fuser -k ${PORT:-5000}/tcp 2>/dev/null || true
}

# Function to handle cleanup and user options
cleanup() {
    # Temporarily ignore SIGINT to prevent recursive calls during menu
    trap '' SIGINT SIGTERM

    echo ""
    echo -e "${BLUE}=========================================="
    echo "Caught Signal (Ctrl+C)..."
    echo -e "==========================================${NC}"
    echo ""
    echo -e "${BLUE}What would you like to do?${NC}"
    echo "  0) Exit"
    echo "  1) Cancel (Continue running)"
    echo "  Any other key) Restart"
    echo ""
    echo -n "Enter your choice: "
    read -r choice </dev/tty

    case "$choice" in
        0)
            echo -e "${GREEN}Exiting SuperMemory...${NC}"
            kill_server
            exit 0
            ;;
        1)
            echo -e "${GREEN}Continuing execution...${NC}"
            # Re-enable trap
            trap cleanup SIGINT
            return 0
            ;;
        *)
            echo -e "${YELLOW}Restarting SuperMemory...${NC}"
            SHOULD_RESTART=1
            kill_server
            # Re-enable trap
            trap cleanup SIGINT
            return 0
            ;;
    esac
}

# Trap Ctrl+C (SIGINT)
trap cleanup SIGINT

# Read FRONTEND_DEV from .env (defaults to false if not set)
FRONTEND_DEV=${FRONTEND_DEV:-false}

# Main loop to support restart
while true; do
    SHOULD_RESTART=0

    # Ensure cleanup of any previous processes
    kill_server

    if [ "$FRONTEND_DEV" = "true" ]; then
        echo -e "${GREEN}Starting Backend and Frontend (Dev Mode)...${NC}"
        echo ""

        # Start Backend in its own session (won't receive terminal signals)
        echo -e "${BLUE}[Backend] Starting Flask...${NC}"
        setsid python app.py </dev/null &
        APP_PID=$!

        # Start Frontend in background
        echo -e "${BLUE}[Frontend] Starting Vite...${NC}"
        (cd frontend && exec setsid npm run dev </dev/null) &
        FRONTEND_PID=$!

        # Wait loop - use a simple polling approach
        while true; do
            # Check if we should restart
            if [ "$SHOULD_RESTART" = "1" ]; then break; fi
            # Check if processes are still running
            if ! kill -0 $APP_PID 2>/dev/null && ! kill -0 $FRONTEND_PID 2>/dev/null; then break; fi
            # Sleep briefly, ignore errors from signal interruption
            sleep 1 2>/dev/null || true
        done
    else
        # Standard production-like start (Backend only)
        echo -e "${GREEN}Starting Backend Only...${NC}"
        # Start in its own session so it won't receive Ctrl+C from terminal
        # Redirect stdin from /dev/null so it's fully detached from terminal input
        setsid python app.py </dev/null &
        APP_PID=$!

        # Wait loop - use a simple polling approach
        while true; do
            # Check if we should restart
            if [ "$SHOULD_RESTART" = "1" ]; then break; fi
            # Check if process is still running
            if ! kill -0 $APP_PID 2>/dev/null; then break; fi
            # Sleep briefly, ignore errors from signal interruption
            sleep 1 2>/dev/null || true
        done
    fi

    # If SHOULD_RESTART is not 1, exit the loop
    if [ "$SHOULD_RESTART" != "1" ]; then
        kill_server
        break
    fi

    echo ""
    echo -e "${BLUE}Restarting...${NC}"
    echo ""
    # Give it a moment to release ports
    sleep 2
done
