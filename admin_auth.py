"""
Admin login and the check every admin endpoint uses.

Admin accounts live in the database (admin_accounts); nothing about them is in the app. Two kinds:
  * standalone admin (user_id NULL): its own hashed password;
  * super admin who is also a member (user_id set): logs in with their member mobile and
    password; the app then asks whether to open the member view or the admin view. Logging in (POST /login with the admin's mobile and password) creates a session
(admin_sessions) and returns a random token. The app sends it on every request as
`Authorization: Bearer <token>`; require_admin() accepts a request only with a valid, unexpired
session. Members flagged isadmin get no admin access.

Create or change the admin with:  python create_admin.py   (prints SQL, or --apply)
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import text
from werkzeug.security import check_password_hash

from model import db
import schema_check

router = Blueprint("admin_auth", __name__)

SESSION_DAYS = 180
IST = timedelta(hours=5, minutes=30)

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS admin_accounts (
           id SERIAL PRIMARY KEY,
           mobile_number VARCHAR(15) NOT NULL UNIQUE,
           name VARCHAR(120) NOT NULL DEFAULT 'Admin',
           password_hash TEXT,
           user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
           is_active BOOLEAN NOT NULL DEFAULT TRUE,
           created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Kolkata')
       )""",
    """CREATE TABLE IF NOT EXISTS admin_sessions (
           id SERIAL PRIMARY KEY,
           admin_id INTEGER NOT NULL REFERENCES admin_accounts(id) ON DELETE CASCADE,
           token_hash CHAR(64) NOT NULL UNIQUE,
           created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Kolkata'),
           expires_at TIMESTAMP NOT NULL
       )""",
    # Tables created before super admins could be members
    "ALTER TABLE admin_accounts ADD COLUMN IF NOT EXISTS user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE admin_accounts ALTER COLUMN password_hash DROP NOT NULL",
]


def _now_ist():
    return datetime.utcnow() + IST


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _tables_ready():
    return schema_check.has("admin_accounts.id") and schema_check.has("admin_sessions.id")


def _bearer_token():
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def find_admin_account(mobile):
    """The active admin account for this mobile number, or None."""
    if not _tables_ready() or not mobile:
        return None
    return db.session.execute(
        text("SELECT id, mobile_number, name, password_hash, user_id FROM admin_accounts "
             "WHERE mobile_number = :m AND is_active"),
        {"m": str(mobile).strip()},
    ).first()


def _new_session(account):
    token = secrets.token_urlsafe(32)
    now = _now_ist()
    db.session.execute(
        text("INSERT INTO admin_sessions (admin_id, token_hash, created_at, expires_at) "
             "VALUES (:a, :h, :c, :e)"),
        {"a": account.id, "h": _hash_token(token), "c": now, "e": now + timedelta(days=SESSION_DAYS)},
    )
    # Housekeeping: drop expired sessions
    db.session.execute(text("DELETE FROM admin_sessions WHERE expires_at < :n"), {"n": now})
    db.session.commit()
    logging.info(f"Admin {account.mobile_number} logged in")
    return token


def admin_login(mobile, password):
    """
    For POST /login, for a standalone admin account. None when this mobile is not one (member
    login follows, see member_admin_token); otherwise (response_dict, status).
    """
    account = find_admin_account(mobile)
    if account is None or account.user_id is not None:
        return None
    if not password or not account.password_hash or not check_password_hash(account.password_hash, password):
        return {"error": "Invalid password"}, 401
    token = _new_session(account)
    return {
        "message": "Login successful",
        "role": "admin",
        "user_id": "admin",
        "admin_token": token,
        "name": account.name,
        "zone_code": "",
        "force_password_change": False,
        "is_quick_registered": False,
    }, 200


def member_admin_token(user_id):
    """
    After a member's password has been checked: a new admin session token when this member is a
    super admin, else None. The app asks them which view to open.
    """
    if not _tables_ready():
        return None
    account = db.session.execute(
        text("SELECT id, mobile_number, name, password_hash, user_id FROM admin_accounts "
             "WHERE user_id = :u AND is_active"),
        {"u": user_id},
    ).first()
    return _new_session(account) if account else None


def current_admin():
    """The admin account behind this request's token, or None."""
    token = _bearer_token()
    if not token or not _tables_ready():
        return None
    return db.session.execute(
        text("SELECT a.id, a.mobile_number, a.name FROM admin_sessions s "
             "JOIN admin_accounts a ON a.id = s.admin_id "
             "WHERE s.token_hash = :h AND s.expires_at > :n AND a.is_active"),
        {"h": _hash_token(token), "n": _now_ist()},
    ).first()


def require_admin():
    """Return (error_response, status_code, admin_label) — error is None when authorised."""
    admin = current_admin()
    if admin is None:
        return jsonify({"error": "Admin login required. Please log in again."}), 401, None
    return None, None, admin.mobile_number


def admin_name_for(value):
    """The admin's name when a stored 'who did it' value is an admin account's mobile, else None."""
    value = str(value or "").strip()
    if not value or not _tables_ready():
        return None
    row = db.session.execute(
        text("SELECT name FROM admin_accounts WHERE mobile_number = :m"), {"m": value}
    ).first()
    return row[0] if row else None


@router.route("/admin/logout", methods=["POST"])
def admin_logout():
    token = _bearer_token()
    if token and _tables_ready():
        db.session.execute(text("DELETE FROM admin_sessions WHERE token_hash = :h"), {"h": _hash_token(token)})
        db.session.commit()
    return jsonify({"message": "Logged out"}), 200


@router.route("/admin/session", methods=["GET"])
def admin_session():
    """Lets the app check on start-up that its saved admin session is still valid."""
    admin = current_admin()
    if admin is None:
        return jsonify({"valid": False}), 401
    return jsonify({"valid": True, "name": admin.name}), 200


def admin_required(view):
    """Decorator: the endpoint answers only for a logged-in admin (valid session token)."""
    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        err, status, _ = require_admin()
        if err:
            return err, status
        return view(*args, **kwargs)
    return wrapper
