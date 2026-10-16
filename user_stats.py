"""
Member statistics for the admin dashboard.

users.created_at is set when a member registers (or an admin quick-registers them).
Members who registered before that were given 1 Jan 2025 (IST) by
migrations/add_user_joined_date.sql; they are reported as "joined_placeholder" so the
dashboard can say that 2025 includes them.

Endpoint
────────
  GET /admin/user-stats    (admin_mobile | admin_user_id)
"""

import logging
from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify
from sqlalchemy import text

from model import db
from admin_auth import require_admin
import schema_check

router = Blueprint("user_stats", __name__)

IST = timedelta(hours=5, minutes=30)
# 1 Jan 2025 00:00 IST: the date given to members who joined before dates were recorded
PLACEHOLDER_IST = "2025-01-01 00:00:00"   # must match migrations/add_user_joined_date.sql
ZONES = ("A", "B", "C")

# users.created_at is stored in IST, so its date is the Indian date.
JOINED_IST = "u.created_at"


def _count(sql, **params):
    return db.session.execute(text(sql), params).scalar() or 0


@router.route("/admin/user-stats", methods=["GET"])
def user_stats():
    err, status, _ = require_admin()
    if err:
        return err, status
    try:
        from upasana_settings import get_booking_settings, get_trial_settings, get_opening_settings

        booking = get_booking_settings()
        booking_year = booking["booking_year"]
        trial = get_trial_settings()
        opens_at = get_opening_settings(booking_year)["booking_opens_at"] if booking_year else None
        today = (datetime.utcnow() + IST).date()

        total = _count("SELECT COUNT(*) FROM users u")
        has_joined = schema_check.has("users.created_at")
        unknown = _count("SELECT COUNT(*) FROM users u WHERE u.created_at IS NULL") if has_joined else total
        placeholder = _count(
            "SELECT COUNT(*) FROM users u WHERE u.created_at = CAST(:p AS TIMESTAMP)", p=PLACEHOLDER_IST
        ) if has_joined else 0

        per_year = [
            {"year": int(y), "count": n}
            for y, n in db.session.execute(text(f"""
                SELECT EXTRACT(YEAR FROM {JOINED_IST})::int, COUNT(*) FROM users u
                WHERE u.created_at IS NOT NULL GROUP BY 1 ORDER BY 1
            """)).all()
        ] if has_joined else []

        zones = {z: 0 for z in ZONES}
        other_zone = 0
        for zone, n in db.session.execute(text("SELECT u.zone_code, COUNT(*) FROM users u GROUP BY 1")).all():
            if zone in zones:
                zones[zone] = n
            else:
                other_zone += n

        def joined_between(start, end):
            """Members who joined on IST dates start..end (inclusive)."""
            if not has_joined:
                return 0
            return _count(
                f"SELECT COUNT(*) FROM users u WHERE u.created_at IS NOT NULL "
                f"AND {JOINED_IST}::date BETWEEN :start AND :end",
                start=start, end=end,
            )

        # Booking season: November and December before the booking year (trial run + opening day).
        season = None
        if booking_year:
            y = booking_year - 1
            opening_day = opens_at[:10] if opens_at else None
            season = {
                "year": y,
                "november": joined_between(date(y, 11, 1), date(y, 11, 30)),
                "december": joined_between(date(y, 12, 1), date(y, 12, 31)),
                "trial_start": trial["trial_run_start"],
                "trial_end": trial["trial_run_end"],
                "during_trial": joined_between(trial["trial_run_start"], trial["trial_run_end"])
                if trial["trial_run_start"] and trial["trial_run_end"] else None,
                "opening_day": opening_day,
                "on_opening_day": joined_between(opening_day, opening_day) if opening_day else None,
            }

        booked = 0
        if booking_year:
            booked = _count(
                "SELECT COUNT(DISTINCT b.user_id) FROM bookings b WHERE b.is_active "
                + ("AND NOT b.is_trial " if schema_check.has("bookings.is_trial") else "")
                + "AND EXTRACT(YEAR FROM b.booking_date) = :y",
                y=booking_year,
            )

        return jsonify({
            "total": total,
            "joined_unknown": unknown,
            "joined_placeholder": placeholder,
            "joined_this_year": next((p["count"] for p in per_year if p["year"] == today.year), 0),
            "joined_last_30_days": joined_between(today - timedelta(days=29), today),
            "per_year": per_year,
            "zones": zones,
            "other_zone": other_zone,
            "anugrahit": _count("SELECT COUNT(*) FROM users u WHERE LOWER(u.anugrahit) = 'yes'"),
            "profile_pending": _count("SELECT COUNT(*) FROM users u WHERE u.is_quick_registered IS TRUE"),
            "booking_year": booking_year,
            "booked_this_year": booked,
            "season": season,
        }), 200
    except Exception as e:
        logging.error(f"Error in user_stats: {e}")
        return jsonify({"error": "Failed to fetch member statistics"}), 500
