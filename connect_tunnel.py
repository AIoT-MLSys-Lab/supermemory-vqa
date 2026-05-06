#!/usr/bin/env python3
"""
SSH Tunnel Connection Script for SuperMemory
Cross-platform script that works on Windows, Linux, and macOS

This script reads configuration from .env and establishes an SSH tunnel
to access the SuperMemory server from a remote machine.

Features:
- Reads SSH_PASSWORD from .env for non-interactive authentication
- Uses paramiko for cross-platform SSH (works on Windows without sshpass)
- Automatic retry with exponential backoff when connection is lost

Usage:
    python connect_tunnel.py
    # or
    python3 connect_tunnel.py
    # or on Unix systems
    ./connect_tunnel.py

Dependencies:
    pip install paramiko
"""

import os
import sys
import platform
import time
import threading
import socket
import select


class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

    @classmethod
    def disable_on_windows(cls):
        """Disable colors on Windows if ANSI support is not available"""
        if platform.system() == 'Windows':
            # Try to enable ANSI colors on Windows 10+
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except:
                # If it fails, disable colors
                cls.CYAN = cls.GREEN = cls.YELLOW = cls.RED = cls.GRAY = cls.RESET = cls.BOLD = ''


def load_env_file(env_path='.env'):
    """
    Load environment variables from .env file

    Args:
        env_path: Path to the .env file (default: '.env')

    Returns:
        dict: Dictionary of environment variables
    """
    env_vars = {}

    if not os.path.exists(env_path):
        return env_vars

    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse KEY=VALUE format
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                env_vars[key] = value

    return env_vars


class SSHTunnelForwarder:
    """SSH Tunnel using paramiko for cross-platform support"""
    
    def __init__(self, ssh_host, ssh_port, ssh_user, ssh_password, 
                 local_port, remote_host, remote_port):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.local_port = local_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.client = None
        self.server_socket = None
        self.running = False
        self.threads = []
    
    def connect(self):
        """Establish SSH connection"""
        import paramiko
        
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        print(f"{Colors.GREEN}Connecting to {self.ssh_host}...{Colors.RESET}")
        
        self.client.connect(
            hostname=self.ssh_host,
            port=self.ssh_port,
            username=self.ssh_user,
            password=self.ssh_password,
            look_for_keys=True,
            allow_agent=True,
            timeout=30
        )
        
        print(f"{Colors.GREEN}SSH connection established!{Colors.RESET}")
    
    def handle_client(self, client_socket):
        """Handle a single client connection through the tunnel"""
        try:
            transport = self.client.get_transport()
            channel = transport.open_channel(
                'direct-tcpip',
                (self.remote_host, self.remote_port),
                client_socket.getpeername()
            )
        except Exception as e:
            print(f"{Colors.RED}Failed to open channel: {e}{Colors.RESET}")
            client_socket.close()
            return
        
        try:
            while self.running:
                r, w, x = select.select([client_socket, channel], [], [], 1.0)
                
                if client_socket in r:
                    data = client_socket.recv(4096)
                    if len(data) == 0:
                        break
                    channel.send(data)
                
                if channel in r:
                    data = channel.recv(4096)
                    if len(data) == 0:
                        break
                    client_socket.send(data)
        except Exception:
            pass
        finally:
            channel.close()
            client_socket.close()
    
    def start(self):
        """Start the tunnel"""
        self.connect()
        
        # Create local listening socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('127.0.0.1', self.local_port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)
        
        self.running = True
        
        print(f"{Colors.GREEN}Tunnel established!{Colors.RESET}")
        print(f"{Colors.YELLOW}Forwarding localhost:{self.local_port} -> {self.remote_host}:{self.remote_port}{Colors.RESET}")
        print()
        print(f"{Colors.GRAY}Press Ctrl+C to close the tunnel{Colors.RESET}")
        print()
        
        try:
            while self.running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket,),
                        daemon=True
                    )
                    thread.start()
                    self.threads.append(thread)
                except socket.timeout:
                    # Check if SSH connection is still alive
                    if self.client and self.client.get_transport():
                        if not self.client.get_transport().is_active():
                            raise Exception("SSH connection lost")
                    continue
        finally:
            self.stop()
    
    def stop(self):
        """Stop the tunnel"""
        self.running = False
        
        if self.server_socket:
            self.server_socket.close()
        
        if self.client:
            self.client.close()


def main():
    """Main function to establish SSH tunnel with retry logic"""

    # Enable colors (or disable on older Windows)
    Colors.disable_on_windows()

    print(f"{Colors.BOLD}{Colors.CYAN}=== SSH Tunnel Configuration ==={Colors.RESET}")

    # Check if .env file exists
    if not os.path.exists('.env'):
        print(f"{Colors.RED}Error: .env file not found{Colors.RESET}")
        print(f"{Colors.YELLOW}Please create a .env file with the following variables:{Colors.RESET}")
        print("  LOCAL_PORT=8080")
        print("  REMOTE_PORT=5000")
        print("  SSH_USER=your_username")
        print("  SERVER_HOST=your_server.example.com")
        print("  SSH_PASSWORD=your_password")
        sys.exit(1)

    # Load environment variables
    env_vars = load_env_file('.env')

    # Get configuration with defaults
    local_port = int(env_vars.get('LOCAL_PORT', '8080'))
    remote_port = int(env_vars.get('REMOTE_PORT', '5000'))
    ssh_user = env_vars.get('SSH_USER', 'alam.140')
    server_host = env_vars.get('SERVER_HOST', 'cse-dnc197057d.coeit.osu.edu')
    ssh_password = env_vars.get('SSH_PASSWORD', '')
    ssh_port = int(env_vars.get('SSH_PORT', '22'))

    # Retry configuration
    max_retries = int(env_vars.get('SSH_MAX_RETRIES', '0'))  # 0 = infinite retries
    initial_retry_delay = int(env_vars.get('SSH_RETRY_DELAY', '5'))  # seconds
    max_retry_delay = int(env_vars.get('SSH_MAX_RETRY_DELAY', '60'))  # seconds

    # Display configuration
    print(f"Local port:  {Colors.GREEN}{local_port}{Colors.RESET}")
    print(f"Remote port: {Colors.GREEN}{remote_port}{Colors.RESET}")
    print(f"SSH user:    {Colors.GREEN}{ssh_user}{Colors.RESET}")
    print(f"Server:      {Colors.GREEN}{server_host}{Colors.RESET}")
    print(f"Password:    {Colors.GREEN}{'configured' if ssh_password else 'not set'}{Colors.RESET}")
    print(f"Auto-retry:  {Colors.GREEN}{'infinite' if max_retries == 0 else max_retries} attempts{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}================================{Colors.RESET}")
    print()

    # Check for paramiko
    try:
        import paramiko
    except ImportError:
        print(f"{Colors.RED}Error: paramiko is not installed{Colors.RESET}")
        print(f"{Colors.YELLOW}Install it with: pip install paramiko{Colors.RESET}")
        sys.exit(1)

    if not ssh_password:
        print(f"{Colors.YELLOW}Warning: SSH_PASSWORD not set in .env{Colors.RESET}")
        print(f"{Colors.YELLOW}Will attempt to use SSH keys or prompt for password{Colors.RESET}")
        print()
        # Prompt for password
        import getpass
        ssh_password = getpass.getpass(f"Enter password for {ssh_user}@{server_host}: ")

    print(f"{Colors.GREEN}Establishing SSH tunnel...{Colors.RESET}")
    print(f"{Colors.YELLOW}Access the application at: http://localhost:{local_port}{Colors.RESET}")
    print()

    # Retry loop
    retry_count = 0
    current_delay = initial_retry_delay

    while True:
        try:
            tunnel = SSHTunnelForwarder(
                ssh_host=server_host,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                ssh_password=ssh_password,
                local_port=local_port,
                remote_host='localhost',
                remote_port=remote_port
            )
            tunnel.start()
            
            # If we get here, tunnel was closed cleanly
            print(f"{Colors.YELLOW}SSH tunnel closed{Colors.RESET}")
            break

        except KeyboardInterrupt:
            print()
            print(f"{Colors.YELLOW}SSH tunnel closed by user{Colors.RESET}")
            sys.exit(0)
            
        except Exception as e:
            retry_count += 1

            # Check if we've exceeded max retries (0 = infinite)
            if max_retries > 0 and retry_count >= max_retries:
                print(f"{Colors.RED}Maximum retry attempts ({max_retries}) reached. Exiting.{Colors.RESET}")
                sys.exit(1)

            print()
            print(f"{Colors.YELLOW}Connection error: {e}{Colors.RESET}")
            print(f"{Colors.YELLOW}Retrying in {current_delay} seconds...{Colors.RESET}")
            print(f"{Colors.GRAY}Retry attempt {retry_count}{' of ' + str(max_retries) if max_retries > 0 else ''}{Colors.RESET}")

            time.sleep(current_delay)

            # Exponential backoff with cap
            current_delay = min(current_delay * 2, max_retry_delay)

            print()
            print(f"{Colors.GREEN}Reconnecting...{Colors.RESET}")


if __name__ == '__main__':
    main()
