from functools import wraps
from flask import session, jsonify


def login_required(role=None):
    """Decorator to protect routes. Usage: @login_required() or @login_required('admin')."""
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({"success": False, "message": "Not logged in"}), 401
            if role and session.get("role") != role:
                return jsonify({"success": False, "message": "Not authorized for this resource"}), 403
            return fn(*args, **kwargs)
        return decorated
    return wrapper
