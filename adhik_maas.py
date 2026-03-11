"""
Adhik Maas Daura Seva – store submissions in PostgreSQL.
- One submission per user; users cannot change or add again after submitting.
- Admin can list and update any user's submission.
Exposes:
  GET  /adhik-maas/areas        → list of Pune areas
  GET  /adhik-maas/map-data     → [admin] list for map: id, name, seva_type, latitude, longitude
  POST /adhik-maas/submit       → store submission (blocked if user already submitted)
  GET  /adhik-maas/submissions  → [admin] list all submissions with user info
  PUT  /adhik-maas/submissions/<id> → [admin] update a submission
"""

import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

router = Blueprint("adhik_maas", __name__)

# Mobile number used for hardcoded admin login in app (no numeric user id)
SUPER_ADMIN_MOBILE = os.getenv("SUPER_ADMIN_MOBILE", "1234567890")

PUNE_AREAS = [
    "Akurdi", "Aundh", "Balewadi", "Baner", "Bavdhan", "Bhosari",
    "Bibwewadi", "Camp", "Chandan Nagar", "Chinchwad", "Deccan Gymkhana",
    "Dhanori", "Dhayari", "Hadapsar", "Hinjewadi", "Kalyani Nagar",
    "Karve Nagar", "Kasba Peth", "Katraj", "Kharadi", "Kondhwa",
    "Koregaon Park", "Kothrud", "Lohegaon", "Magarpatta", "Model Colony",
    "Moshi", "Mundhwa", "Narayan Peth", "NIBM Road", "Nigdi", "Pashan",
    "Pimple Saudagar", "Pimpri", "Ravet", "Sadashiv Peth", "Shaniwar Peth",
    "Shivaji Nagar", "Sinhagad Road", "Swargate", "Undri", "Viman Nagar",
    "Vishrantwadi", "Wadgaon Sheri", "Wagholi", "Wakad", "Wanowrie", "Yerwada",
]


def _require_admin():
    """Return (error_response, status_code) if not admin, else (None, None)."""
    from model import User
    data = request.get_json(silent=True) or {}
    admin_user_id = request.args.get("admin_user_id") or data.get("admin_user_id")
    admin_mobile = request.args.get("admin_mobile") or data.get("admin_mobile")

    if admin_mobile and str(admin_mobile).strip() == SUPER_ADMIN_MOBILE:
        return None, None
    if not admin_user_id:
        return jsonify({"error": "admin_user_id or admin_mobile (for super admin) is required"}), 401
    try:
        admin_user_id = int(admin_user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid admin_user_id"}), 401
    user = User.query.get(admin_user_id)
    if not user or not getattr(user, "isadmin", False):
        return jsonify({"error": "Admin access required"}), 403
    return None, None


@router.route("/adhik-maas/areas", methods=["GET"])
def get_areas():
    """Return list of Pune areas for the dropdown."""
    return jsonify({"areas": PUNE_AREAS}), 200


def _geocode_address(address):
    """Convert full_address to (lat, lon) using Nominatim. Returns (None, None) on failure."""
    if not address or not str(address).strip():
        return None, None
    try:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
        geolocator = Nominatim(user_agent="upasana-adhik-maas")
        rate_limited = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
        location = rate_limited(str(address).strip())
        if location and location.latitude is not None and location.longitude is not None:
            return float(location.latitude), float(location.longitude)
    except Exception as e:
        logging.warning("Geocode failed for %s: %s", address[:50] if address else "", e)
    return None, None


@router.route("/adhik-maas/map-data", methods=["GET"])
def get_map_data():
    """[Admin] Return list of submissions with coordinates for map: id, name, seva_type, latitude, longitude."""
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import db, AdhikMaasSubmission, User

    submissions = AdhikMaasSubmission.query.order_by(AdhikMaasSubmission.submitted_at.desc()).all()
    out = []
    for s in submissions:
        u = User.query.get(s.user_id)
        if not u:
            continue
        name = f"{u.first_name} {u.last_name}".strip() or f"User #{s.user_id}"
        seva_type = s.seva_label or s.seva_preference or ""
        address = getattr(u, "full_address", None)
        lat, lon = None, None
        if getattr(u, "latitude", None) is not None and getattr(u, "longitude", None) is not None:
            try:
                lat = float(u.latitude)
                lon = float(u.longitude)
            except (TypeError, ValueError):
                pass
        if (lat is None or lon is None) and address:
            lat, lon = _geocode_address(address)
            if lat is not None and lon is not None:
                try:
                    u.latitude = lat
                    u.longitude = lon
                    db.session.add(u)
                    db.session.commit()
                except Exception as e:
                    logging.warning("Failed to save lat/lng for user %s: %s", s.user_id, e)
                    db.session.rollback()
        if lat is None or lon is None:
            lat, lon = 18.5204, 73.8567
        out.append({
            "id": s.id,
            "user_id": s.user_id,
            "name": name,
            "seva_type": seva_type,
            "seva_preference": s.seva_preference,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
        })
    return jsonify(out), 200


@router.route("/adhik-maas/submit", methods=["POST"])
def submit_adhik_maas():
    """
    Accept Adhik Maas Daura Seva submission. One per user; if user already
    submitted, returns 409 and does not allow change or new submission.
    Body: { "user_id": ..., "seva_preference": ..., "area": ... }
    """
    from model import db, AdhikMaasSubmission

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}

    user_id = data.get("user_id")
    seva_preference = data.get("seva_preference")
    area = (data.get("area") or "").strip()

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    if not seva_preference:
        return jsonify({"error": "seva_preference is required"}), 400
    if not area:
        return jsonify({"error": "area is required"}), 400
    if area not in PUNE_AREAS:
        return jsonify({"error": f"area must be one of: {PUNE_AREAS}"}), 400

    try:
        existing = AdhikMaasSubmission.query.filter_by(user_id=int(user_id)).first()
        if existing:
            return jsonify({
                "error": "You have already submitted your response for Adhik Maas seva. Only one submission per user is allowed.",
                "already_submitted": True,
            }), 409
    except Exception:
        pass

    submitted_at = data.get("submitted_at")
    if submitted_at:
        try:
            submitted_at = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            submitted_at = datetime.utcnow()
    else:
        submitted_at = datetime.utcnow()

    try:
        entry = AdhikMaasSubmission(
            user_id=int(user_id),
            seva_preference=seva_preference,
            seva_label=data.get("seva_label", "") or "",
            area=area,
            submitted_at=submitted_at,
        )
        db.session.add(entry)
        db.session.commit()
        return jsonify({"message": "Submission saved", "id": entry.id}), 201
    except Exception as e:
        db.session.rollback()
        logging.exception("adhik_maas submit error: %s", e)
        return jsonify({"error": "Failed to save submission"}), 500


@router.route("/adhik-maas/submissions", methods=["GET"])
def list_submissions_admin():
    """[Admin] List all Adhik Maas submissions with user details."""
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import db, AdhikMaasSubmission, User

    submissions = AdhikMaasSubmission.query.order_by(AdhikMaasSubmission.submitted_at.desc()).all()
    out = []
    for s in submissions:
        u = User.query.get(s.user_id)
        out.append({
            "id": s.id,
            "user_id": s.user_id,
            "user_name": f"{u.first_name} {u.last_name}" if u else "",
            "user_mobile": getattr(u, "mobile_number", None) if u else None,
            "user_zone_code": getattr(u, "zone_code", None) if u else None,
            "user_area": getattr(u, "area", None) if u else None,
            "full_address": getattr(u, "full_address", None) if u else None,
            "seva_preference": s.seva_preference,
            "seva_label": s.seva_label,
            "area": s.area,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        })
    return jsonify({"submissions": out}), 200


@router.route("/adhik-maas/submissions/<int:submission_id>", methods=["PUT"])
def update_submission_admin(submission_id):
    """[Admin] Update a user's Adhik Maas submission."""
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import db, AdhikMaasSubmission

    data = request.get_json(force=True, silent=True) or {}
    seva_preference = data.get("seva_preference")
    seva_label = data.get("seva_label", "")
    area = (data.get("area") or "").strip()

    submission = AdhikMaasSubmission.query.get(submission_id)
    if not submission:
        return jsonify({"error": "Submission not found"}), 404

    if seva_preference is not None:
        submission.seva_preference = seva_preference
    if seva_label is not None:
        submission.seva_label = seva_label
    if area:
        if area not in PUNE_AREAS:
            return jsonify({"error": f"area must be one of: {PUNE_AREAS}"}), 400
        submission.area = area

    try:
        db.session.commit()
        return jsonify({
            "message": "Submission updated",
            "id": submission.id,
            "user_id": submission.user_id,
            "seva_preference": submission.seva_preference,
            "seva_label": submission.seva_label,
            "area": submission.area,
        }), 200
    except Exception as e:
        db.session.rollback()
        logging.exception("adhik_maas admin update error: %s", e)
        return jsonify({"error": "Failed to update submission"}), 500
