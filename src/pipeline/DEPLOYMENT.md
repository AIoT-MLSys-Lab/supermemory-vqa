# Server Deployment Guide

This guide explains how to deploy SuperMemory on a server and access it from other machines on the same network.

## Overview

This setup allows you to:
- Deploy SuperMemory on server: **cse-cnc197058s.coeit.osu.edu** (username: alam.140)
- Access the application from another PC: **cse-dnc197057d** on the same network
- Share the application with other machines on the local network

## Prerequisites

1. **SSH access** to the server (cse-cnc197058s.coeit.osu.edu)
2. **Python 3.10+** installed on the server
3. **Network connectivity** between machines on the same network
4. **Firewall permissions** to allow traffic on the application port (default: 5000)

## Quick Start

### 1. Deploy to Server

From your local machine, use the deployment script:

```bash
./deploy_server.sh
```

This will:
- Copy all necessary files to the server via SCP
- Install dependencies
- Set up the environment
- Start the application

### 2. Manual Deployment

If you prefer manual deployment:

```bash
# SSH into the server
ssh alam.140@cse-cnc197058s.coeit.osu.edu

# Clone or copy the repository
cd ~
git clone <repository-url> supermemory
# OR copy files via scp (see below)

# Navigate to the directory
cd supermemory

# Run the server start script
./start_server.sh
```

### 3. Access from Another Machine

Once the server is running, access the application from any machine on the same network


cess (Alternative Method)

If direct network access is blocked by firewalls, you can use SSH port forwarding to access the server from a remote machine.

#### Using the Python Script

Works on **all platforms** (Windows, Linux, macOS):

```bash
python connect_tunnel.py
```

Or if `python3` is required:

```bash
python3 connect_tunnel.py
```

The Python script automatically:
- Detects your operating system
- Finds the SSH client
- Reads configuration from `.env`
- Provides helpful error messages if SSH is not installed

#### Accessing the Application

After running the script, access the application in your browser at:

```
http://localhost:8080
```

The tunnel script reads configuration from the `.env` file:

```bash
# SSH Tunnel Configuration
LOCAL_PORT=8080        # Port on your local machine
REMOTE_PORT=5000       # Port on the server
SSH_USER=xxxx      # Your SSH username
SERVER_HOST=xxxx # Server hostname
```

To close the tunnel, press `Ctrl+C` in the terminal where the script is running.

## Configuration

### Environment Variables

Create a `.env` file on the server with:

```bash
# Required: Your Gemini API key
GEMINI_API_KEY=your_gemini_api_key_here

# Network access: bind to all interfaces
HOST=0.0.0.0

# Port (default: 5000)
PORT=5000

# Debug mode (use 'false' for production)
DEBUG=false

# SSH Tunnel Configuration (for remote access via SSH)
LOCAL_PORT=8080
REMOTE_PORT=5000
SSH_USER=xxxx
SERVER_HOST=xxxx
```
