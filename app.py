"""
Flask Application for Video Annotation Review Platform

Automatically builds the Svelte frontend if Node.js is available.
"""
import subprocess
import platform
import sys
import os
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('init_script')

def get_latest_mtime(directory):
    """Recursively find the latest modification time in a directory."""
    latest_mtime = 0
    for root, _, files in os.walk(directory):
        # Skip node_modules and hidden git files for speed
        if 'node_modules' in root or '.git' in root:
            continue
            
        for file in files:
            filepath = os.path.join(root, file)
            try:
                mtime = os.path.getmtime(filepath)
                if mtime > latest_mtime:
                    latest_mtime = mtime
            except OSError:
                continue
    return latest_mtime

def build_frontend():
    """Build the Svelte frontend if source is newer than build or Node is available."""
    frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
    static_frontend = os.path.join(os.path.dirname(__file__), 'static', 'frontend')
    build_artifact = os.path.join(static_frontend, 'index.html')
    
    # 1. Check if frontend source exists
    if not os.path.exists(os.path.join(frontend_dir, 'package.json')):
        logger.error("Frontend source not found at frontend/")
        print("ERROR: Frontend source not found at frontend/")
        return False
    
    # 2. Check if build is fresh
    needs_build = True
    if os.path.exists(build_artifact):
        print("Checking for frontend updates...")
        last_build_time = os.path.getmtime(build_artifact)
        last_source_change = get_latest_mtime(frontend_dir)
        
        if last_source_change < last_build_time:
            logger.info("Frontend is up to date.")
            print("Frontend is up to date. Access at http://localhost:5000/app")
            needs_build = False
        else:
            logger.info("Frontend source has changed. Rebuilding...")
            print("Frontend source has changed. Rebuilding...")

    if not needs_build:
        return True

    # 3. Determine platform-specific npm command
    system_platform = platform.system().lower()
    npm_cmd = 'npm.cmd' if system_platform == 'windows' else 'npm'
    
    # 4. Check if npm is actually installed/working
    try:
        subprocess.run([npm_cmd, '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Node.js not found. Cannot rebuild frontend.")
        print("Node.js not found. Cannot rebuild frontend.")
        if os.path.exists(build_artifact):
            logger.info("Using existing (potentially stale) build.")
            print("Using existing (potentially stale) build.")
            return True
        else:
            logger.error("No build found. Using legacy templates.")
            print("No build found. Using legacy templates.")
            return False
    
    print(f"Building Svelte frontend in {frontend_dir}...")
    try:
        # 5. Install & Build
        # We only run install if package.json is newer than node_modules (optional optimization)
        # but running it every time is safer and usually fast if cached.
        subprocess.run([npm_cmd, 'install', "--verbose"], cwd=frontend_dir, check=True)
        subprocess.run([npm_cmd, 'run', 'build'], cwd=frontend_dir, check=True)
        
        print("Frontend built successfully! Access at http://localhost:5000/app")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Frontend build failed: {e}")
        print(f"Frontend build failed: {e}")
        if os.path.exists(build_artifact):
             logger.info("Falling back to previous build.")
             print("Falling back to previous build.")
             return True
        return False


from visualization.app import app

if __name__ == '__main__':
    # Try to build frontend on startup
    build_frontend()
    
    # Use debug mode only in development (when DEBUG env var is set)
    debug_mode = os.getenv('DEBUG', 'False').lower() == 'true'
    print("\nStarting SuperMemory server...")
    print("  UI: http://localhost:5000/")
    logger.info(f"Starting app with debug_mode={debug_mode}")
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
