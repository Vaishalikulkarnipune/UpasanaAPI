import os
from flask import request, jsonify
from model import User

SUPER_ADMIN_MOBILE = os.getenv("SUPER_ADMIN_MOBILE", "1234567890")


def require_admin():
    """Return (error_response, status_code, admin_label) — error is None when authorised."""
    data = request.get_json(silent=True) or {}
    admin_user_id = request.args.get("admin_user_id") or data.get("admin_user_id")
    admin_mobile  = request.args.get("admin_mobile")  or data.get("admin_mobile")

    if admin_mobile and str(admin_mobile).strip() == SUPER_ADMIN_MOBILE:
        return None, None, SUPER_ADMIN_MOBILE
    if not admin_user_id:
        return jsonify({"error": "admin_user_id or admin_mobile required"}), 401, None
    try:
        admin_user_id = int(admin_user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid admin_user_id"}), 401, None
    user = User.query.get(admin_user_id)
    if not user or not getattr(user, "isadmin", False):
        return jsonify({"error": "Admin access required"}), 403, None
    return None, None, str(admin_user_id)
