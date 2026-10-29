"""
Zone coordinators (व्यवस्थापक), one per zone, kept in the database so an admin can change the
name and numbers from Admin Settings without an app update.

  GET  /zone-coordinators           public: [{zone_code, name, phone, area}]  (the app caches it)
  POST /admin/zone-coordinators     admin: { coordinators: [{zone_code, name, phone, area?}] }

The table is created and filled with the current coordinators when the API starts (and by
migrations/add_zone_coordinators.sql); later starts leave the admin's changes alone.
"""
import logging
import re

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from admin_auth import require_admin
from model import db
import schema_check

router = Blueprint("zone_coordinators", __name__)

ZONES = ("A", "B", "C")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS zone_coordinators (
           zone_code VARCHAR(5) PRIMARY KEY,
           name VARCHAR(120) NOT NULL,
           phone VARCHAR(10) NOT NULL,
           area VARCHAR(80),
           updated_at TIMESTAMP,
           updated_by VARCHAR(120)
       )""",
    # Current coordinators (only when the zone has no row yet)
    """INSERT INTO zone_coordinators (zone_code, name, phone, area) VALUES
           ('A', 'Umesh Jaltare', '9373100155', 'East Pune'),
           ('B', 'Ajinkya Deshpande', '9404439445', 'Rest of Pune'),
           ('C', 'Hrishikesh Mayee', '9987966798', 'PCMC')
       ON CONFLICT (zone_code) DO NOTHING""",
]


def ready():
    return schema_check.has("zone_coordinators.zone_code")


def _rows():
    rows = db.session.execute(
        text("SELECT zone_code, name, phone, area FROM zone_coordinators ORDER BY zone_code")
    ).all()
    return [{"zone_code": r[0], "name": r[1], "phone": r[2], "area": r[3] or ""} for r in rows]


@router.route("/zone-coordinators", methods=["GET"])
def list_coordinators():
    if not ready():
        return jsonify({"coordinators": [], "available": False}), 200
    return jsonify({"coordinators": _rows(), "available": True}), 200


@router.route("/admin/zone-coordinators", methods=["POST"])
def save_coordinators():
    err, status, admin_label = require_admin()
    if err:
        return err, status
    if not ready():
        return jsonify({"error": "Zone coordinators are not available yet. Please try again later."}), 503

    data = request.get_json(silent=True) or {}
    items = data.get("coordinators")
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Send the coordinators to save."}), 400

    clean = []
    for item in items:
        zone = str((item or {}).get("zone_code", "")).strip().upper()
        name = re.sub(r"\s+", " ", str(item.get("name", "")).strip())[:120]
        phone = re.sub(r"\D", "", str(item.get("phone", "")))[-10:]
        area = str(item.get("area", "") or "").strip()[:80]
        if zone not in ZONES:
            return jsonify({"error": f"Unknown zone: {zone or '(empty)'}."}), 400
        if not name:
            return jsonify({"error": f"Zone {zone}: enter the coordinator's name."}), 400
        if len(phone) != 10:
            return jsonify({"error": f"Zone {zone}: enter a 10-digit mobile number."}), 400
        clean.append((zone, name, phone, area))

    try:
        for zone, name, phone, area in clean:
            db.session.execute(
                text("""INSERT INTO zone_coordinators (zone_code, name, phone, area, updated_at, updated_by)
                        VALUES (:z, :n, :p, NULLIF(:a, ''), NOW() AT TIME ZONE 'Asia/Kolkata', :by)
                        ON CONFLICT (zone_code) DO UPDATE SET name = :n, phone = :p,
                          area = COALESCE(NULLIF(:a, ''), zone_coordinators.area),
                          updated_at = NOW() AT TIME ZONE 'Asia/Kolkata', updated_by = :by"""),
                {"z": zone, "n": name, "p": phone, "a": area, "by": (admin_label or "")[:120]},
            )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.exception(f"save_coordinators failed: {e}")
        return jsonify({"error": "Could not save the coordinators. Please try again."}), 500
    logging.info(f"Admin {admin_label} updated zone coordinators: {[c[0] for c in clean]}")
    return jsonify({"message": "Coordinators saved.", "coordinators": _rows()}), 200
