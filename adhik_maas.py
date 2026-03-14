"""
Adhik Maas Daura Seva – store submissions in PostgreSQL.

Endpoints
─────────
User-facing
  GET  /adhik-maas/areas                       list of Pune areas
  GET  /adhik-maas/my-submission?user_id=X     current user's submission
  POST /adhik-maas/submit                      new submission (one per user)
  PUT  /adhik-maas/my-submission               user edits own submission (toggle-gated)

Admin
  GET  /adhik-maas/submissions                 all submissions with full user info
  PUT  /adhik-maas/submissions/<id>            update any submission
  GET  /adhik-maas/summary                     aggregated stats + permutation combinations
  PUT  /adhik-maas/submissions/<id>/shortlist  shortlist or un-shortlist a user
  GET  /adhik-maas/shortlisted                 list shortlisted users
  PUT  /adhik-maas/submissions/<id>/finalize   finalize or un-finalize a user
  GET  /adhik-maas/finalized                   list finalized users
  GET  /adhik-maas/map-data                    map: id, name, seva_type, lat, lon
"""

import os
import logging
from collections import defaultdict
from datetime import datetime
from flask import Blueprint, request, jsonify

router = Blueprint("adhik_maas", __name__)

SUPER_ADMIN_MOBILE = os.getenv("SUPER_ADMIN_MOBILE", "1234567890")

# Kept as a last-resort fallback only; the real source of truth is the DB.
_FALLBACK_AREAS: list[str] = []


def _get_area_lookup() -> dict[str, dict]:
    """
    Return {area_name_lower: {area_name, route_number, route_name, pin_code}}
    from the DB.  Used to validate areas and enrich submissions.
    """
    from model import AdhikMaasArea
    rows = AdhikMaasArea.query.filter_by(is_active=True).all()
    return {
        r.area_name.lower(): {
            "area_name":    r.area_name,
            "route_number": r.route_number,
            "route_name":   r.route_name,
            "pin_code":     r.pin_code,
        }
        for r in rows
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _require_admin():
    """Return (error_response, status_code) if not admin, else (None, None)."""
    from model import User
    data = request.get_json(silent=True) or {}
    admin_user_id = request.args.get("admin_user_id") or data.get("admin_user_id")
    admin_mobile  = request.args.get("admin_mobile")  or data.get("admin_mobile")

    if admin_mobile and str(admin_mobile).strip() == SUPER_ADMIN_MOBILE:
        return None, None
    if not admin_user_id:
        return jsonify({"error": "admin_user_id or admin_mobile required"}), 401
    try:
        admin_user_id = int(admin_user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid admin_user_id"}), 401
    user = User.query.get(admin_user_id)
    if not user or not getattr(user, "isadmin", False):
        return jsonify({"error": "Admin access required"}), 403
    return None, None


def _parse_seva_flags(seva_preference: str) -> dict:
    """
    Derive boolean flags + time slot from the pipe-separated seva_preference
    string the frontend sends (e.g. "padyapuja|seva|afternoon|shejarti").
    Also handles legacy values from the old three-option model.
    """
    parts = set((seva_preference or "").split("|"))
    has_padyapuja       = "padyapuja"  in parts or seva_preference == "padya_puja"
    has_seva_mahaprasad = "seva"       in parts or seva_preference == "abhishek_mahaprasad"
    has_shejarti        = "shejarti"   in parts or seva_preference == "shejarti_kakad_aarti"
    seva_time = next(
        (p for p in ["afternoon", "evening", "any"] if p in parts),
        "any" if seva_preference == "abhishek_mahaprasad" else None,
    )
    return {
        "has_padyapuja":       has_padyapuja,
        "has_seva_mahaprasad": has_seva_mahaprasad,
        "seva_time":           seva_time,
        "has_shejarti":        has_shejarti,
    }


def _apply_flags(submission, seva_preference: str):
    """Write parsed flags onto a submission ORM object in-place."""
    flags = _parse_seva_flags(seva_preference)
    submission.has_padyapuja       = flags["has_padyapuja"]
    submission.has_seva_mahaprasad = flags["has_seva_mahaprasad"]
    submission.seva_time           = flags["seva_time"]
    submission.has_shejarti        = flags["has_shejarti"]


def _submission_dict(s, u=None):
    """Serialise an AdhikMaasSubmission + optional User into a dict."""
    return {
        "id":                   s.id,
        "user_id":              s.user_id,
        "user_name":            f"{u.first_name} {u.last_name}".strip() if u else "",
        "user_mobile":          getattr(u, "mobile_number", None) if u else None,
        "user_zone_code":       getattr(u, "zone_code", None)     if u else None,
        "user_area":            getattr(u, "area", None)          if u else None,
        "full_address":         getattr(u, "full_address", None)  if u else None,
        # raw
        "seva_preference":      s.seva_preference,
        "seva_label":           s.seva_label,
        "area":                 s.area,
        "route_number":         s.route_number,
        "route_name":           s.route_name,
        "pin_code":             s.pin_code,
        # structured flags
        "has_padyapuja":        bool(s.has_padyapuja),
        "has_seva_mahaprasad":  bool(s.has_seva_mahaprasad),
        "seva_time":            s.seva_time,
        "has_shejarti":         bool(s.has_shejarti),
        # workflow
        "is_shortlisted":       bool(s.is_shortlisted),
        "shortlisted_at":       s.shortlisted_at.isoformat()  if s.shortlisted_at  else None,
        "is_finalized":         bool(s.is_finalized),
        "finalized_at":         s.finalized_at.isoformat()    if s.finalized_at    else None,
        "admin_notes":          s.admin_notes,
        "submitted_at":         s.submitted_at.isoformat()    if s.submitted_at    else None,
    }


# ─── Public endpoints ─────────────────────────────────────────────────────────

@router.route("/adhik-maas/areas", methods=["GET"])
def get_areas():
    """
    Return active areas grouped by route.
    Optional query param: ?pin_code=411014  → filters to areas matching that pin.
    Optional query param: ?q=baner          → filters by area name substring.

    Response:
    {
      "routes": [
        {
          "route_number": "1A",
          "route_name": "North-East ...",
          "areas": [
            { "area_name": "Vishrantwadi", "pin_code": "411015" },
            ...
          ]
        }
      ],
      "flat": ["Vishrantwadi", ...]   ← all area names, for simple text search
    }
    """
    from model import AdhikMaasArea
    from collections import OrderedDict

    pin_filter = (request.args.get("pin_code") or "").strip()
    q_filter   = (request.args.get("q") or "").strip().lower()

    query = AdhikMaasArea.query.filter_by(is_active=True)
    if pin_filter:
        query = query.filter(AdhikMaasArea.pin_code == pin_filter)
    rows = query.order_by(AdhikMaasArea.route_number, AdhikMaasArea.sort_order).all()

    if q_filter:
        rows = [r for r in rows if q_filter in r.area_name.lower() or q_filter in r.pin_code]

    # Group into ordered dict by route
    route_map: OrderedDict = OrderedDict()
    for r in rows:
        key = r.route_number
        if key not in route_map:
            route_map[key] = {"route_number": r.route_number, "route_name": r.route_name, "areas": []}
        route_map[key]["areas"].append({"area_name": r.area_name, "pin_code": r.pin_code})

    return jsonify({
        "routes": list(route_map.values()),
        "flat":   [r.area_name for r in rows],
    }), 200


@router.route("/adhik-maas/my-submission", methods=["GET"])
def get_my_submission():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user_id"}), 400

    from model import AdhikMaasSubmission
    s = AdhikMaasSubmission.query.filter_by(user_id=user_id).first()
    if not s:
        return jsonify({"submitted": False}), 200

    return jsonify({
        "submitted":        True,
        "id":               s.id,
        "seva_preference":  s.seva_preference,
        "seva_label":       s.seva_label,
        "area":             s.area,
        "has_padyapuja":    bool(s.has_padyapuja),
        "has_seva_mahaprasad": bool(s.has_seva_mahaprasad),
        "seva_time":        s.seva_time,
        "has_shejarti":     bool(s.has_shejarti),
        "submitted_at":     s.submitted_at.isoformat() if s.submitted_at else None,
    }), 200


@router.route("/adhik-maas/submit", methods=["POST"])
def submit_adhik_maas():
    from model import db, AdhikMaasSubmission
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}

    user_id         = data.get("user_id")
    seva_preference = data.get("seva_preference")
    area            = (data.get("area") or "").strip()

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    if not seva_preference:
        return jsonify({"error": "seva_preference is required"}), 400
    if not area:
        return jsonify({"error": "area is required"}), 400

    area_lookup = _get_area_lookup()
    area_info   = area_lookup.get(area.lower())
    if not area_info:
        return jsonify({"error": "area must be one of the allowed areas"}), 400

    try:
        existing = AdhikMaasSubmission.query.filter_by(user_id=int(user_id)).first()
        if existing:
            return jsonify({
                "error": "You have already submitted. Only one submission per user is allowed.",
                "already_submitted": True,
            }), 409
    except Exception:
        pass

    submitted_at = data.get("submitted_at")
    try:
        submitted_at = datetime.fromisoformat(submitted_at.replace("Z", "+00:00")) if submitted_at else datetime.utcnow()
    except (ValueError, TypeError, AttributeError):
        submitted_at = datetime.utcnow()

    try:
        entry = AdhikMaasSubmission(
            user_id         = int(user_id),
            seva_preference = seva_preference,
            seva_label      = data.get("seva_label", "") or "",
            area            = area_info["area_name"],
            route_number    = area_info["route_number"],
            route_name      = area_info["route_name"],
            pin_code        = area_info["pin_code"],
            submitted_at    = submitted_at,
        )
        _apply_flags(entry, seva_preference)
        db.session.add(entry)
        db.session.commit()
        return jsonify({"message": "Submission saved", "id": entry.id}), 201
    except Exception as e:
        db.session.rollback()
        logging.exception("adhik_maas submit error: %s", e)
        return jsonify({"error": "Failed to save submission"}), 500


@router.route("/adhik-maas/my-submission", methods=["PUT"])
def update_my_submission():
    from model import db, AdhikMaasSubmission, FeatureToggle

    toggle = FeatureToggle.query.filter_by(toggle_name="allow_adhik_maas_edit").first()
    if not toggle or not toggle.toggle_enabled:
        return jsonify({"error": "Editing submissions is currently disabled by admin."}), 403

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}

    user_id         = data.get("user_id")
    seva_preference = data.get("seva_preference")
    area            = (data.get("area") or "").strip()

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    if not seva_preference:
        return jsonify({"error": "seva_preference is required"}), 400
    if not area:
        return jsonify({"error": "area is required"}), 400

    area_lookup = _get_area_lookup()
    area_info   = area_lookup.get(area.lower())
    if not area_info:
        return jsonify({"error": "area must be one of the allowed areas"}), 400

    try:
        submission = AdhikMaasSubmission.query.filter_by(user_id=int(user_id)).first()
        if not submission:
            return jsonify({"error": "No existing submission found for this user."}), 404

        submission.seva_preference = seva_preference
        submission.seva_label      = data.get("seva_label", "") or ""
        submission.area            = area_info["area_name"]
        submission.route_number    = area_info["route_number"]
        submission.route_name      = area_info["route_name"]
        submission.pin_code        = area_info["pin_code"]
        _apply_flags(submission, seva_preference)
        db.session.commit()
        return jsonify({"message": "Submission updated", **_submission_dict(submission)}), 200
    except Exception as e:
        db.session.rollback()
        logging.exception("adhik_maas user update error: %s", e)
        return jsonify({"error": "Failed to update submission"}), 500


# ─── Admin: list / update ──────────────────────────────────────────────────────

@router.route("/adhik-maas/submissions", methods=["GET"])
def list_submissions_admin():
    """[Admin] All submissions with full user info and workflow status."""
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import AdhikMaasSubmission, User

    submissions = AdhikMaasSubmission.query.order_by(AdhikMaasSubmission.submitted_at.desc()).all()
    out = [_submission_dict(s, User.query.get(s.user_id)) for s in submissions]
    return jsonify({"submissions": out, "total": len(out)}), 200


@router.route("/adhik-maas/submissions/<int:submission_id>", methods=["PUT"])
def update_submission_admin(submission_id):
    """[Admin] Update seva preference / area / notes for any submission."""
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import db, AdhikMaasSubmission

    data            = request.get_json(force=True, silent=True) or {}
    seva_preference = data.get("seva_preference")
    seva_label      = data.get("seva_label", "")
    area            = (data.get("area") or "").strip()
    admin_notes     = data.get("admin_notes")

    submission = AdhikMaasSubmission.query.get(submission_id)
    if not submission:
        return jsonify({"error": "Submission not found"}), 404

    if seva_preference is not None:
        submission.seva_preference = seva_preference
        _apply_flags(submission, seva_preference)
    if seva_label is not None:
        submission.seva_label = seva_label
    if area:
        area_lookup = _get_area_lookup()
        area_info   = area_lookup.get(area.lower())
        if not area_info:
            return jsonify({"error": "area must be one of the allowed areas"}), 400
        submission.area         = area_info["area_name"]
        submission.route_number = area_info["route_number"]
        submission.route_name   = area_info["route_name"]
        submission.pin_code     = area_info["pin_code"]
    if admin_notes is not None:
        submission.admin_notes = admin_notes

    try:
        db.session.commit()
        return jsonify({"message": "Submission updated", **_submission_dict(submission)}), 200
    except Exception as e:
        db.session.rollback()
        logging.exception("adhik_maas admin update error: %s", e)
        return jsonify({"error": "Failed to update submission"}), 500


# ─── Admin: summary / permutation combinations ────────────────────────────────

@router.route("/adhik-maas/summary", methods=["GET"])
def get_summary_admin():
    """
    [Admin] Aggregated statistics and every permutation combination that
    actually exists in the data, so the admin can see which preference
    bundles are popular and plan assignments accordingly.

    Response shape:
    {
      "total": N,
      "shortlisted": N,
      "finalized": N,
      "seva_counts": {
        "padyapuja": N,
        "seva_mahaprasad": N,
        "shejarti": N
      },
      "time_counts": { "afternoon": N, "evening": N, "any": N, "none": N },
      "area_counts": { "<area>": N, ... },
      "combinations": [
        {
          "has_padyapuja": true,
          "has_seva_mahaprasad": true,
          "seva_time": "afternoon",
          "has_shejarti": false,
          "count": N,
          "users": [ { "id", "user_id", "user_name", "area", ... } ]
        },
        ...
      ]
    }
    """
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import AdhikMaasSubmission, User

    all_subs = AdhikMaasSubmission.query.order_by(AdhikMaasSubmission.area).all()

    # ── totals
    total       = len(all_subs)
    shortlisted = sum(1 for s in all_subs if s.is_shortlisted)
    finalized   = sum(1 for s in all_subs if s.is_finalized)

    # ── seva breakdown
    seva_counts = {
        "padyapuja":      sum(1 for s in all_subs if s.has_padyapuja),
        "seva_mahaprasad":sum(1 for s in all_subs if s.has_seva_mahaprasad),
        "shejarti":       sum(1 for s in all_subs if s.has_shejarti),
    }

    # ── time breakdown
    time_counts = defaultdict(int)
    for s in all_subs:
        key = s.seva_time if s.seva_time else "none"
        time_counts[key] += 1

    # ── area breakdown
    area_counts = defaultdict(int)
    for s in all_subs:
        area_counts[s.area or "Unknown"] += 1

    # ── route breakdown
    route_counts: dict = {}
    for s in all_subs:
        key = s.route_number or "Unknown"
        if key not in route_counts:
            route_counts[key] = {"route_number": key, "route_name": s.route_name or "", "count": 0}
        route_counts[key]["count"] += 1

    # ── permutation combinations
    combo_map = defaultdict(list)
    for s in all_subs:
        u   = User.query.get(s.user_id)
        key = (
            bool(s.has_padyapuja),
            bool(s.has_seva_mahaprasad),
            s.seva_time or "none",
            bool(s.has_shejarti),
        )
        combo_map[key].append(_submission_dict(s, u))

    combinations = []
    for (padya, seva_mp, time, shejarti), users in sorted(combo_map.items(), key=lambda x: -len(x[1])):
        combinations.append({
            "has_padyapuja":       padya,
            "has_seva_mahaprasad": seva_mp,
            "seva_time":           time if time != "none" else None,
            "has_shejarti":        shejarti,
            "count":               len(users),
            "users":               users,
        })

    return jsonify({
        "total":        total,
        "shortlisted":  shortlisted,
        "finalized":    finalized,
        "seva_counts":  dict(seva_counts),
        "time_counts":  dict(time_counts),
        "area_counts":  dict(area_counts),
        "route_counts": sorted(route_counts.values(), key=lambda x: x["route_number"]),
        "combinations": combinations,
    }), 200


# ─── Admin: shortlist workflow ─────────────────────────────────────────────────

@router.route("/adhik-maas/submissions/<int:submission_id>/shortlist", methods=["PUT"])
def toggle_shortlist(submission_id):
    """
    [Admin] Shortlist or remove from shortlist.
    Body: { "shortlisted": true|false, "admin_notes": "..." (optional) }
    """
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import db, AdhikMaasSubmission

    data       = request.get_json(force=True, silent=True) or {}
    shortlisted = data.get("shortlisted", True)

    submission = AdhikMaasSubmission.query.get(submission_id)
    if not submission:
        return jsonify({"error": "Submission not found"}), 404

    submission.is_shortlisted  = bool(shortlisted)
    submission.shortlisted_at  = datetime.utcnow() if shortlisted else None
    if "admin_notes" in data:
        submission.admin_notes = data["admin_notes"]

    try:
        db.session.commit()
        return jsonify({
            "message":         "Shortlist updated",
            "id":              submission.id,
            "is_shortlisted":  submission.is_shortlisted,
            "shortlisted_at":  submission.shortlisted_at.isoformat() if submission.shortlisted_at else None,
        }), 200
    except Exception as e:
        db.session.rollback()
        logging.exception("shortlist toggle error: %s", e)
        return jsonify({"error": "Failed to update shortlist"}), 500


@router.route("/adhik-maas/shortlisted", methods=["GET"])
def list_shortlisted():
    """[Admin] Return only shortlisted submissions."""
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import AdhikMaasSubmission, User

    subs = AdhikMaasSubmission.query.filter_by(is_shortlisted=True).order_by(AdhikMaasSubmission.area).all()
    out  = [_submission_dict(s, User.query.get(s.user_id)) for s in subs]
    return jsonify({"shortlisted": out, "total": len(out)}), 200


# ─── Admin: finalize workflow ──────────────────────────────────────────────────

@router.route("/adhik-maas/submissions/<int:submission_id>/finalize", methods=["PUT"])
def toggle_finalize(submission_id):
    """
    [Admin] Finalize or un-finalize a user.
    Body: { "finalized": true|false, "admin_notes": "..." (optional) }
    """
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import db, AdhikMaasSubmission

    data      = request.get_json(force=True, silent=True) or {}
    finalized = data.get("finalized", True)

    submission = AdhikMaasSubmission.query.get(submission_id)
    if not submission:
        return jsonify({"error": "Submission not found"}), 404

    submission.is_finalized = bool(finalized)
    submission.finalized_at = datetime.utcnow() if finalized else None
    if "admin_notes" in data:
        submission.admin_notes = data["admin_notes"]

    try:
        db.session.commit()
        return jsonify({
            "message":       "Finalize status updated",
            "id":            submission.id,
            "is_finalized":  submission.is_finalized,
            "finalized_at":  submission.finalized_at.isoformat() if submission.finalized_at else None,
        }), 200
    except Exception as e:
        db.session.rollback()
        logging.exception("finalize toggle error: %s", e)
        return jsonify({"error": "Failed to update finalize status"}), 500


@router.route("/adhik-maas/finalized", methods=["GET"])
def list_finalized():
    """[Admin] Return only finalized submissions."""
    err, status = _require_admin()
    if err is not None:
        return err, status
    from model import AdhikMaasSubmission, User

    subs = AdhikMaasSubmission.query.filter_by(is_finalized=True).order_by(AdhikMaasSubmission.area).all()
    out  = [_submission_dict(s, User.query.get(s.user_id)) for s in subs]
    return jsonify({"finalized": out, "total": len(out)}), 200


# ─── Admin: map data ──────────────────────────────────────────────────────────

def _geocode_address(address):
    if not address or not str(address).strip():
        return None, None
    try:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
        geolocator  = Nominatim(user_agent="upasana-adhik-maas")
        rate_limited = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
        location    = rate_limited(str(address).strip())
        if location and location.latitude is not None:
            return float(location.latitude), float(location.longitude)
    except Exception as e:
        logging.warning("Geocode failed for %s: %s", (address or "")[:50], e)
    return None, None


@router.route("/adhik-maas/map-data", methods=["GET"])
def get_map_data():
    """[Admin] Submissions with coordinates for map view."""
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
        name      = f"{u.first_name} {u.last_name}".strip() or f"User #{s.user_id}"
        seva_type = s.seva_label or s.seva_preference or ""
        address   = getattr(u, "full_address", None)
        lat = lon = None
        if getattr(u, "latitude", None) is not None and getattr(u, "longitude", None) is not None:
            try:
                lat, lon = float(u.latitude), float(u.longitude)
            except (TypeError, ValueError):
                pass
        if (lat is None or lon is None) and address:
            lat, lon = _geocode_address(address)
            if lat is not None:
                try:
                    u.latitude  = lat
                    u.longitude = lon
                    db.session.add(u)
                    db.session.commit()
                except Exception as e:
                    logging.warning("Failed to save lat/lng for user %s: %s", s.user_id, e)
                    db.session.rollback()
        if lat is None or lon is None:
            lat, lon = 18.5204, 73.8567
        out.append({
            "id":               s.id,
            "user_id":          s.user_id,
            "name":             name,
            "seva_type":        seva_type,
            "seva_preference":  s.seva_preference,
            "has_padyapuja":    bool(s.has_padyapuja),
            "has_seva_mahaprasad": bool(s.has_seva_mahaprasad),
            "seva_time":        s.seva_time,
            "has_shejarti":     bool(s.has_shejarti),
            "is_shortlisted":   bool(s.is_shortlisted),
            "is_finalized":     bool(s.is_finalized),
            "latitude":         round(lat, 6),
            "longitude":        round(lon, 6),
        })
    return jsonify(out), 200
