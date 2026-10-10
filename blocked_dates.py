"""
Admin-blocked Upasana dates.

Endpoints
─────────
  GET    /blocked-dates?year=YYYY            list blocked dates (year optional)
  POST   /admin/blocked-dates                block one or more dates
         body: { dates: ["YYYY-MM-DD", ...], reason?, admin_mobile | admin_user_id }
  DELETE /admin/blocked-dates/<YYYY-MM-DD>   unblock a date
         query: admin_mobile | admin_user_id
"""

import logging
from datetime import datetime, date
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError, OperationalError

from model import db, BlockedDate
from admin_auth import require_admin
from Booking import lock_month, taken_dates

router = Blueprint("blocked_dates", __name__)


def _parse_date(value):
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _to_dict(b):
    return {
        "date": b.blocked_date.strftime("%Y-%m-%d"),
        "reason": b.reason or "",
        "created_by": b.created_by,
        "created_at": b.created_at.strftime("%Y-%m-%d %H:%M:%S") if b.created_at else None,
    }


@router.route("/blocked-dates", methods=["GET"])
def list_blocked_dates():
    try:
        query = BlockedDate.query
        year = request.args.get("year", type=int)
        if year:
            query = query.filter(
                BlockedDate.blocked_date >= date(year, 1, 1),
                BlockedDate.blocked_date <= date(year, 12, 31),
            )
        rows = query.order_by(BlockedDate.blocked_date).all()
        return jsonify({"blocked_dates": [_to_dict(b) for b in rows]}), 200
    except Exception as e:
        logging.error(f"Error in list_blocked_dates: {e}")
        return jsonify({"error": "Failed to fetch blocked dates"}), 500


@router.route("/admin/blocked-dates", methods=["POST"])
def block_dates():
    err, status, admin_label = require_admin()
    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    raw_dates = data.get("dates") or ([data["date"]] if data.get("date") else [])
    reason = (str(data.get("reason") or "").strip())[:255] or None

    if not raw_dates:
        return jsonify({"error": "At least one date is required."}), 400

    dates = []
    for raw in raw_dates:
        d = _parse_date(raw)
        if not d:
            return jsonify({"error": f"Invalid date '{raw}'. Use YYYY-MM-DD."}), 400
        if d not in dates:
            dates.append(d)

    try:
        # Same month locks as bookings, so a booking in flight can't slip in
        # between the check and the insert. Sorted to keep lock order stable.
        for year, month in sorted({(d.year, d.month) for d in dates}):
            lock_month(year, month)

        booked = sorted(d.strftime("%Y-%m-%d") for d in taken_dates(dates))
        if booked:
            db.session.rollback()
            return jsonify({
                "error": "These dates already have an active booking or event. Cancel it first.",
                "booked_dates": booked,
            }), 409

        already = {
            b.blocked_date for b in BlockedDate.query.filter(BlockedDate.blocked_date.in_(dates)).all()
        }
        to_block = [d for d in dates if d not in already]
        for d in to_block:
            db.session.add(BlockedDate(blocked_date=d, reason=reason, created_by=admin_label))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Some dates were blocked by another admin at the same time. Refresh and try again."}), 409
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in block_dates: {e}")
        return jsonify({"error": "Failed to block dates"}), 500

    return jsonify({
        "message": f"{len(to_block)} date(s) blocked.",
        "blocked": [d.strftime("%Y-%m-%d") for d in to_block],
        "already_blocked": sorted(d.strftime("%Y-%m-%d") for d in already),
    }), 201


@router.route("/admin/blocked-dates/<date_str>", methods=["DELETE"])
def unblock_date(date_str):
    err, status, _ = require_admin()
    if err:
        return err, status

    d = _parse_date(date_str)
    if not d:
        return jsonify({"error": "Invalid date. Use YYYY-MM-DD."}), 400

    try:
        deleted = BlockedDate.query.filter_by(blocked_date=d).delete()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in unblock_date: {e}")
        return jsonify({"error": "Failed to unblock date"}), 500

    if not deleted:
        return jsonify({"error": "Date is not blocked."}), 404
    return jsonify({"message": f"{date_str} unblocked."}), 200
