"""
Shared Flask extensions used across visualization module.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Central limiter instance so routes can share configuration
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)
