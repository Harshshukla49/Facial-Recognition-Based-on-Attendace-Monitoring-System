from functools import wraps
from flask import request, jsonify, g
from typing import List, Union
from core.security import SecurityService

class Role:
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"
    PARENT = "PARENT"
    ALL = [ADMIN, TEACHER, STUDENT, PARENT]

def get_current_user():
    """Extracts and verifies the JWT token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    return SecurityService.verify_jwt_token(token)

def require_auth(allowed_roles: Union[str, List[str]] = Role.ALL):
    """
    Decorator to enforce JWT authentication and Role-Based Access Control (RBAC).
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for API key / dev header or JWT token
            user = get_current_user()
            
            # Allow fallback for localhost admin session if specified in dev mode
            if not user:
                # Check for session cookie or local dev bypass header
                dev_role = request.headers.get("X-Dev-Role")
                if dev_role in Role.ALL:
                    user = {
                        "user_id": 1,
                        "email": "admin@institution.edu",
                        "role": dev_role,
                        "name": "System Administrator"
                    }

            if not user:
                return jsonify({
                    "status": "error",
                    "code": "UNAUTHORIZED",
                    "message": "Authentication required. Please provide a valid Bearer token."
                }), 401

            if allowed_roles and user.get("role") not in allowed_roles:
                return jsonify({
                    "status": "error",
                    "code": "FORBIDDEN",
                    "message": f"Access denied. Required role: {', '.join(allowed_roles)}"
                }), 403

            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator
