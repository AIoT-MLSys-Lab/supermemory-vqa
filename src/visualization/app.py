"""
Visualization API for annotation review and editing.
"""
import logging
import os
import sys
from flask import Flask
from flask_compress import Compress

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from visualization.config import apply_default_config  # noqa: E402
from visualization.routes import annotation_bp, prompt_bp, video_bp, caption_bp  # noqa: E402
from visualization.security import generate_csrf_token  # noqa: E402


def create_app() -> Flask:
    """Factory to create and configure the Flask application."""
    app = Flask(
        __name__,
        static_folder='../../static'
    )

    apply_default_config(app)

    # Enable response compression for better performance
    Compress(app)

    @app.before_request
    def before_request():
        """Add CSRF token to session before each request."""
        generate_csrf_token()

    app.register_blueprint(video_bp)
    app.register_blueprint(prompt_bp)
    app.register_blueprint(annotation_bp)
    app.register_blueprint(caption_bp)

    return app


app = create_app()


if __name__ == '__main__':
    debug_mode = os.getenv('DEBUG', 'False').lower() == 'true'
    host = os.getenv('HOST', 'localhost')
    port = int(os.getenv('PORT', '5000'))

    logger.info("Starting application on %s:%s (debug=%s)", host, port, debug_mode)
    app.run(debug=debug_mode, host=host, port=port)
