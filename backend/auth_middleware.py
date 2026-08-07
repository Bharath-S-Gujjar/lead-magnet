"""Reusable JWT authentication and authorization decorators."""

from functools import wraps

import jwt
from flask import current_app, g, jsonify, request


def _unauthorized(message):
    return jsonify({"success": False, "message": message, "errors": []}), 401


def token_required(view):
    """Require a valid bearer JWT and store its decoded claims on ``flask.g``."""
    @wraps(view)
    def decorated(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return _unauthorized("Authorization token required")

        try:
            g.current_user = jwt.decode(
                token,
                current_app.config["JWT_SECRET"],
                algorithms=["HS256"],
            )
        except jwt.ExpiredSignatureError:
            return _unauthorized("Token has expired")
        except jwt.InvalidTokenError:
            return _unauthorized("Invalid token")

        return view(*args, **kwargs)

    return decorated


def admin_required(view):
    """Require a valid JWT whose role claim is ``admin``."""
    @token_required
    @wraps(view)
    def decorated(*args, **kwargs):
        if g.current_user.get("role") != "admin":
            return jsonify({
                "success": False,
                "message": "Admin access required",
                "errors": [],
            }), 403
        return view(*args, **kwargs)

    return decorated
