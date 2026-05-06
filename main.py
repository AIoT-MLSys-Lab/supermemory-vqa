"""
Main entry point for the SuperMemory Video Annotation Platform
"""
import sys
import os

# Check Python version
if sys.version_info < (3, 10):
    print("Error: Python 3.10 or higher is required.")
    print(f"Current version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print("\nPlease upgrade Python:")
    print("  - Visit https://www.python.org/downloads/")
    print("  - Or use pyenv: pyenv install 3.10 && pyenv global 3.10")
    sys.exit(1)

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from visualization.app import app

if __name__ == '__main__':
    # Use debug mode only in development (when DEBUG env var is set)
    debug_mode = os.getenv('DEBUG', 'False').lower() == 'true'
    # For production, bind to localhost. For external access, set HOST env var to 0.0.0.0
    host = os.getenv('HOST', 'localhost')
    port = int(os.getenv('PORT', '5000'))
    
    print("="*60)
    print("Starting SuperMemory Video Annotation Platform")
    print("="*60)
    print(f"Server: http://{host}:{port}")
    print(f"Debug mode: {debug_mode}")
    print("="*60)
    
    app.run(debug=debug_mode, host=host, port=port)
