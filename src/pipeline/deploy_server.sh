#!/bin/bash
# Deployment script for SuperMemory on a remote server
# This script deploys the application to cse-cnc197058s.coeit.osu.edu

set -e  # Exit on error

# Configuration
SERVER_USER="alam.140"
SERVER_HOST="cse-cnc197058s.coeit.osu.edu"
SERVER_PATH="~/supermemory"
REMOTE="${SERVER_USER}@${SERVER_HOST}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================="
echo "SuperMemory Server Deployment"
echo -e "==========================================${NC}"
echo ""
echo "Target: ${REMOTE}"
echo "Path: ${SERVER_PATH}"
echo ""

# Check if we can reach the server
echo -e "${YELLOW}Checking server connectivity...${NC}"
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "${REMOTE}" "echo 'Connected'" 2>/dev/null; then
    echo -e "${RED}❌ Cannot connect to ${REMOTE}${NC}"
    echo "Please ensure:"
    echo "  1. SSH access is configured"
    echo "  2. SSH keys are set up (or you'll be prompted for password)"
    echo "  3. Server is reachable on the network"
    echo ""
    echo "Try: ssh ${REMOTE}"
    exit 1
fi
echo -e "${GREEN}✓ Server is reachable${NC}"
echo ""

# Create deployment directory on server
echo -e "${YELLOW}Creating deployment directory...${NC}"
ssh "${REMOTE}" "mkdir -p ${SERVER_PATH}"
echo -e "${GREEN}✓ Directory created${NC}"
echo ""

# Copy files to server
echo -e "${YELLOW}Copying files to server...${NC}"
echo "This may take a moment..."

# Create a temporary directory for deployment
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

# Copy files to temp directory (excluding unnecessary files)
rsync -av \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='node_modules' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='uploads/*' \
    --exclude='.env' \
    --exclude='*.log' \
    --exclude='.pytest_cache' \
    --exclude='htmlcov' \
    --exclude='.coverage' \
    ./ "${TEMP_DIR}/"

# Copy to server
rsync -avz --progress "${TEMP_DIR}/" "${REMOTE}:${SERVER_PATH}/"
echo -e "${GREEN}✓ Files copied successfully${NC}"
echo ""

# Check if .env exists on server, if not, copy .env.example
echo -e "${YELLOW}Setting up environment configuration...${NC}"
ssh "${REMOTE}" "cd ${SERVER_PATH} && if [ ! -f .env ]; then cp .env.example .env && echo 'Created .env from .env.example'; fi"
echo -e "${GREEN}✓ Environment file ready${NC}"
echo ""

# Check Python version on server
echo -e "${YELLOW}Checking Python version on server...${NC}"
PYTHON_VERSION=$(ssh "${REMOTE}" "python3 --version" 2>&1 || echo "not found")
echo "Server Python: ${PYTHON_VERSION}"

if [[ "${PYTHON_VERSION}" == *"not found"* ]]; then
    echo -e "${RED}❌ Python 3 not found on server${NC}"
    echo "Please install Python 3.10 or higher on the server"
    exit 1
fi

# Check if version is 3.10+
PYTHON_MAJOR=$(ssh "${REMOTE}" "python3 -c 'import sys; print(sys.version_info.major)'")
PYTHON_MINOR=$(ssh "${REMOTE}" "python3 -c 'import sys; print(sys.version_info.minor)'")

if [ "${PYTHON_MAJOR}" -lt 3 ] || ([ "${PYTHON_MAJOR}" -eq 3 ] && [ "${PYTHON_MINOR}" -lt 10 ]); then
    echo -e "${RED}❌ Python 3.10+ required, found ${PYTHON_MAJOR}.${PYTHON_MINOR}${NC}"
    echo "Please upgrade Python on the server"
    exit 1
fi
echo -e "${GREEN}✓ Python version compatible${NC}"
echo ""

# Create virtual environment and install dependencies
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
ssh "${REMOTE}" "cd ${SERVER_PATH} && python3 -m venv venv"
echo -e "${GREEN}✓ Virtual environment created${NC}"
echo ""

echo -e "${YELLOW}Installing dependencies...${NC}"
ssh "${REMOTE}" "cd ${SERVER_PATH} && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Make scripts executable
echo -e "${YELLOW}Making scripts executable...${NC}"
ssh "${REMOTE}" "cd ${SERVER_PATH} && chmod +x *.sh"
echo -e "${GREEN}✓ Scripts are executable${NC}"
echo ""

# Display next steps
echo -e "${GREEN}=========================================="
echo "✓ Deployment completed successfully!"
echo -e "==========================================${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo "1. Configure the application:"
echo "   ssh ${REMOTE}"
echo "   cd ${SERVER_PATH}"
echo "   nano .env"
echo ""
echo "   Important settings:"
echo "   - Set your GEMINI_API_KEY"
echo "   - Set HOST=0.0.0.0 (for network access)"
echo "   - Set PORT=5000 (or your preferred port)"
echo "   - Set DEBUG=false (for production)"
echo ""
echo "2. Start the server:"
echo "   ssh ${REMOTE}"
echo "   cd ${SERVER_PATH}"
echo "   ./start_server.sh"
echo ""
echo "3. Access from other machines:"
echo "   http://${SERVER_HOST}:5000"
echo "   or"
echo "   http://<server-ip>:5000"
echo ""
echo "4. (Optional) Set up as a system service for automatic startup"
echo "   See DEPLOYMENT.md for instructions"
echo ""
echo -e "${BLUE}Troubleshooting:${NC}"
echo "   - See DEPLOYMENT.md for detailed instructions"
echo "   - Check logs: tail -f ${SERVER_PATH}/supermemory.log"
echo "   - Test connectivity: curl http://localhost:5000"
echo ""
