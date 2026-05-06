#!/bin/bash
# Interactive deployment helper for SuperMemory
# Provides a simple menu interface for common deployment tasks

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

show_banner() {
    echo -e "${BLUE}"
    echo "=========================================="
    echo "   SuperMemory Deployment Helper"
    echo "=========================================="
    echo -e "${NC}"
}

show_menu() {
    echo ""
    echo -e "${CYAN}What would you like to do?${NC}"
    echo ""
    echo "  1) Deploy to remote server"
    echo "  2) Start server (local or SSH)"
    echo "  3) Run troubleshooting diagnostics"
    echo "  4) Configure .env file"
    echo "  5) Show deployment status"
    echo "  6) View documentation"
    echo "  7) Setup systemd service"
    echo "  0) Exit"
    echo ""
}

deploy_to_server() {
    echo -e "${BLUE}=== Deploy to Remote Server ===${NC}"
    echo ""
    
    if [ ! -f "deploy_server.sh" ]; then
        echo -e "${RED}Error: deploy_server.sh not found${NC}"
        return 1
    fi
    
    echo "This will deploy SuperMemory to the server using deploy_server.sh"
    echo "Default target: alam.140@cse-cnc197058s.coeit.osu.edu"
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ./deploy_server.sh
    else
        echo "Deployment cancelled"
    fi
}

start_server() {
    echo -e "${BLUE}=== Start Server ===${NC}"
    echo ""
    echo "1) Start on this machine"
    echo "2) Start on remote server (SSH)"
    echo "0) Back to main menu"
    echo ""
    read -p "Choose option: " -n 1 -r
    echo
    
    case $REPLY in
        1)
            if [ ! -f "start_server.sh" ]; then
                echo -e "${RED}Error: start_server.sh not found${NC}"
                return 1
            fi
            ./start_server.sh
            ;;
        2)
            echo ""
            read -p "Enter SSH connection (e.g., user@hostname): " ssh_target
            # Validate SSH target format (basic validation for user@host)
            if [[ ! "$ssh_target" =~ ^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+$ ]]; then
                echo -e "${RED}Invalid SSH target format. Use: user@hostname${NC}"
                return 1
            fi
            echo "Connecting to ${ssh_target} and starting server..."
            ssh -t "${ssh_target}" "cd ~/supermemory && ./start_server.sh"
            ;;
        0)
            return 0
            ;;
        *)
            echo "Invalid option"
            ;;
    esac
}

run_diagnostics() {
    echo -e "${BLUE}=== Run Diagnostics ===${NC}"
    echo ""
    
    if [ ! -f "troubleshoot.sh" ]; then
        echo -e "${RED}Error: troubleshoot.sh not found${NC}"
        return 1
    fi
    
    ./troubleshoot.sh
    echo ""
    read -p "Press Enter to continue..."
}

configure_env() {
    echo -e "${BLUE}=== Configure Environment ===${NC}"
    echo ""
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            echo "Creating .env from .env.example..."
            cp .env.example .env
            echo -e "${GREEN}✓ Created .env file${NC}"
        else
            echo -e "${RED}Error: .env.example not found${NC}"
            return 1
        fi
    fi
    
    echo "Current configuration:"
    echo ""
    grep -E "^(GEMINI_API_KEY|HOST|PORT|DEBUG)=" .env 2>/dev/null || echo "No configuration found"
    echo ""
    echo "What would you like to do?"
    echo ""
    echo "1) Edit .env manually"
    echo "2) Set GEMINI_API_KEY"
    echo "3) Enable network access (HOST=0.0.0.0)"
    echo "4) Change port"
    echo "5) Toggle debug mode"
    echo "0) Back to main menu"
    echo ""
    read -p "Choose option: " -n 1 -r
    echo
    
    case $REPLY in
        1)
            ${EDITOR:-nano} .env
            ;;
        2)
            # Read API key without echoing it to terminal
            read -s -p "Enter your Gemini API key: " api_key
            echo  # New line after hidden input
            # Escape special characters for sed (& \ / are special in replacement)
            escaped_key=$(printf '%s\n' "$api_key" | sed 's/[&/\]/\\&/g')
            sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=${escaped_key}|" .env
            echo -e "${GREEN}✓ API key updated${NC}"
            ;;
        3)
            sed -i 's/^HOST=.*/HOST=0.0.0.0/' .env
            echo -e "${GREEN}✓ Network access enabled (HOST=0.0.0.0)${NC}"
            ;;
        4)
            read -p "Enter port number (default 5000): " port
            port=${port:-5000}
            # Validate port number
            if ! [[ "$port" =~ ^[0-9]+$ ]] || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
                echo -e "${RED}Invalid port number. Must be 1-65535${NC}"
                return 1
            fi
            sed -i "s/^PORT=.*/PORT=${port}/" .env
            echo -e "${GREEN}✓ Port set to ${port}${NC}"
            ;;
        5)
            current_debug=$(grep "^DEBUG=" .env | cut -d'=' -f2)
            if [ "$current_debug" = "true" ]; then
                sed -i 's/^DEBUG=.*/DEBUG=false/' .env
                echo -e "${GREEN}✓ Debug mode disabled${NC}"
            else
                sed -i 's/^DEBUG=.*/DEBUG=true/' .env
                echo -e "${YELLOW}⚠ Debug mode enabled (use false for production)${NC}"
            fi
            ;;
        0)
            return 0
            ;;
        *)
            echo "Invalid option"
            ;;
    esac
}

show_status() {
    echo -e "${BLUE}=== Deployment Status ===${NC}"
    echo ""
    
    # Check if files exist
    echo -e "${CYAN}Files:${NC}"
    [ -f ".env" ] && echo -e "${GREEN}✓${NC} .env exists" || echo -e "${RED}✗${NC} .env missing"
    [ -d "venv" ] && echo -e "${GREEN}✓${NC} Virtual environment exists" || echo -e "${YELLOW}⚠${NC} Virtual environment missing"
    [ -f "app.py" ] && echo -e "${GREEN}✓${NC} app.py exists" || echo -e "${RED}✗${NC} app.py missing"
    
    echo ""
    
    # Check configuration
    if [ -f ".env" ]; then
        echo -e "${CYAN}Configuration:${NC}"
        HOST_VALUE=$(grep "^HOST=" .env | cut -d'=' -f2)
        PORT_VALUE=$(grep "^PORT=" .env | cut -d'=' -f2)
        DEBUG_VALUE=$(grep "^DEBUG=" .env | cut -d'=' -f2)
        API_KEY=$(grep "^GEMINI_API_KEY=" .env | cut -d'=' -f2)
        
        echo "  HOST: ${HOST_VALUE}"
        echo "  PORT: ${PORT_VALUE}"
        echo "  DEBUG: ${DEBUG_VALUE}"
        
        if [ "$API_KEY" = "your_gemini_api_key_here" ] || [ -z "$API_KEY" ]; then
            echo -e "  API Key: ${YELLOW}Not configured${NC}"
        else
            echo -e "  API Key: ${GREEN}Configured${NC}"
        fi
    fi
    
    echo ""
    
    # Check if server is running
    echo -e "${CYAN}Server Status:${NC}"
    if command -v netstat &> /dev/null; then
        port=${PORT_VALUE:-5000}
        if netstat -tuln 2>/dev/null | grep -q ":${port} "; then
            echo -e "${GREEN}✓${NC} Server appears to be running on port ${port}"
        else
            echo -e "${YELLOW}⚠${NC} Server not detected on port ${port}"
        fi
    else
        echo "  Cannot check (netstat not available)"
    fi
    
    echo ""
    read -p "Press Enter to continue..."
}

view_documentation() {
    echo -e "${BLUE}=== Documentation ===${NC}"
    echo ""
    echo "Available documentation files:"
    echo ""
    echo "1) QUICKSTART_DEPLOYMENT.md - Quick deployment guide"
    echo "2) DEPLOYMENT.md - Complete deployment documentation"
    echo "3) DEPLOYMENT_FILES.md - Overview of deployment files"
    echo "4) README.md - Application documentation"
    echo "0) Back to main menu"
    echo ""
    read -p "Choose document to view: " -n 1 -r
    echo
    
    case $REPLY in
        1)
            [ -f "QUICKSTART_DEPLOYMENT.md" ] && less QUICKSTART_DEPLOYMENT.md || echo "File not found"
            ;;
        2)
            [ -f "DEPLOYMENT.md" ] && less DEPLOYMENT.md || echo "File not found"
            ;;
        3)
            [ -f "DEPLOYMENT_FILES.md" ] && less DEPLOYMENT_FILES.md || echo "File not found"
            ;;
        4)
            [ -f "README.md" ] && less README.md || echo "File not found"
            ;;
        0)
            return 0
            ;;
        *)
            echo "Invalid option"
            ;;
    esac
}

setup_systemd() {
    echo -e "${BLUE}=== Setup systemd Service ===${NC}"
    echo ""
    
    if [ ! -f "supermemory.service" ]; then
        echo -e "${RED}Error: supermemory.service template not found${NC}"
        return 1
    fi
    
    echo "This will help you set up SuperMemory as a systemd service."
    echo "The service will start automatically on boot."
    echo ""
    echo "Steps:"
    echo "1. Edit supermemory.service to match your configuration"
    echo "2. Copy to /etc/systemd/system/ (requires sudo)"
    echo "3. Enable and start the service"
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled"
        return 0
    fi
    
    echo ""
    echo "Opening supermemory.service for editing..."
    echo "Update the paths to match your installation"
    echo ""
    read -p "Press Enter to edit..."
    ${EDITOR:-nano} supermemory.service
    
    echo ""
    echo "To complete setup, run these commands:"
    echo ""
    echo "  sudo cp supermemory.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable supermemory"
    echo "  sudo systemctl start supermemory"
    echo "  sudo systemctl status supermemory"
    echo ""
    read -p "Run these commands now? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo cp supermemory.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable supermemory
        sudo systemctl start supermemory
        echo ""
        sudo systemctl status supermemory
    fi
}

# Main loop
main() {
    show_banner
    
    while true; do
        show_menu
        read -p "Enter choice [0-7]: " -n 1 -r
        echo
        
        case $REPLY in
            1)
                deploy_to_server
                ;;
            2)
                start_server
                ;;
            3)
                run_diagnostics
                ;;
            4)
                configure_env
                ;;
            5)
                show_status
                ;;
            6)
                view_documentation
                ;;
            7)
                setup_systemd
                ;;
            0)
                echo -e "${GREEN}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option. Please try again.${NC}"
                sleep 1
                ;;
        esac
    done
}

# Run main function
main
