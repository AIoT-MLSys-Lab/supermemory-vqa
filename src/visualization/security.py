"""
Security helpers for CSRF handling.
"""
import secrets
from flask import session, current_app


def generate_csrf_token() -> str:
    """Generate and store CSRF token in session."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def verify_csrf_token(token: str) -> bool:
    """Verify provided CSRF token against session."""
    if current_app and current_app.config.get('TESTING', False):
        return True
    return bool(token and token == session.get('csrf_token'))


def extract_csrf_token(request) -> str:
    """Extract CSRF token from headers, JSON body, form data, or query string."""
    header_token = request.headers.get('X-CSRF-Token')
    if header_token:
        return header_token

    json_payload = request.get_json(silent=True) or {}
    if isinstance(json_payload, dict):
        json_token = json_payload.get('csrf_token')
        if json_token:
            return json_token

    form_token = request.form.get('csrf_token') if request.form else None
    if form_token:
        return form_token

    return request.args.get('csrf_token') or ''
