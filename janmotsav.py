from flask import Blueprint, request, jsonify
from datetime import datetime
from model import db, JanmotsavYear, JanmotsavDay, JanmotsavAttendance

router = Blueprint("janmotsav", __name__)

# ==========================================================
# GET CURRENT CONFIG
# ==========================================================
@router.get("/janmotsav/config/current")
def get_current_config():
    """Return the currently active Janmotsav configuration."""
    year = JanmotsavYear.query.filter_by(is_current=True, is_deleted=False).first()

    if not year:
        return jsonify({"error": "No current Janmotsav year set"}), 200

    days = (
        JanmotsavDay.query
            .filter_by(year_id=year.id, is_deleted=False)
            .order_by(JanmotsavDay.event_date)
            .all()
    )

    return jsonify({
        "year": year.year,
        "year_id": year.id,
        "event_name": year.event_name,
        "is_current": year.is_current,
        "location_name": year.location_name,
        "location_url": year.location_url,
        "facebook_url": year.facebook_url,
        "youtube_url": year.youtube_url,
        "instagram_url": year.instagram_url,
        "custom_link_1": year.custom_link_1,
        "custom_link_2": year.custom_link_2,
        "description": year.description,
        "days": [
            {
                "day_id": d.id,
                "date": d.event_date.isoformat(),
                "breakfast": d.breakfast,
                "lunch": d.lunch,
                "evesnacks": d.evesnacks,
                "dinner": d.dinner,
            }
            for d in days
        ]
    })


# ==========================================================
# SAVE ATTENDANCE
# ==========================================================
@router.post("/janmotsav/attendance/save")
def save_attendance():
    """Create or update attendance for the given user and year."""
    data = request.json

    user_id = data["user_id"]
    year_id = data["year_id"]

    try:
        for entry in data["attendance"]:
            day_id = entry["day_id"]

            existing = JanmotsavAttendance.query.filter_by(
                user_id=user_id, year_id=year_id, day_id=day_id, is_deleted=False
            ).first()

            if existing:
                # Update existing attendance
                existing.breakfast_count = entry.get("breakfast", 0)
                existing.lunch_count = entry.get("lunch", 0)
                existing.evesnacks_count = entry.get("evesnacks", 0)
                existing.dinner_count = entry.get("dinner", 0)
                existing.seva_nidhi = entry.get("seva_nidhi", False)
                existing.updated_at = datetime.utcnow()

            else:
                # Insert new attendance
                rec = JanmotsavAttendance(
                    user_id=user_id,
                    year_id=year_id,
                    day_id=day_id,
                    breakfast_count=entry.get("breakfast", 0),
                    lunch_count=entry.get("lunch", 0),
                    evesnacks_count=entry.get("evesnacks", 0),
                    dinner_count=entry.get("dinner", 0),
                    seva_nidhi=entry.get("seva_nidhi", False),
                )
                db.session.add(rec)

        db.session.commit()
        return jsonify({"status": "success"})

    except Exception as e:
        db.session.rollback()
        print("Error saving attendance:", e)
        return jsonify({"error": "Failed to save attendance"}), 500


# ==========================================================
# CREATE YEAR (ADMIN)
# ==========================================================
@router.post("/janmotsav/admin/year/create")
def create_or_update_year():
    """Create or Update a Janmotsav year."""
    data = request.json
    year_id = data.get("id")  # if id present → update

    try:
        # If new year is marked current, unset previous ones
        if data.get("is_current"):
            JanmotsavYear.query.update({"is_current": False})

        if year_id:
            # ---- UPDATE MODE ----
            year = JanmotsavYear.query.get(year_id)
            if not year:
                return jsonify({"error": "Year not found"}), 404

            year.year = data.get("year", year.year)
            year.is_current = data.get("is_current", year.is_current)
            year.event_name = data.get("event_name", year.event_name)
            year.location_name = data.get("location_name", year.location_name)
            year.location_url = data.get("location_url", year.location_url)
            year.facebook_url = data.get("facebook_url", year.facebook_url)
            year.youtube_url = data.get("youtube_url", year.youtube_url)
            year.instagram_url = data.get("instagram_url", year.instagram_url)
            year.custom_link_1 = data.get("custom_link_1", year.custom_link_1)
            year.custom_link_2 = data.get("custom_link_2", year.custom_link_2)
            year.description = data.get("description", year.description)

            db.session.commit()
            return jsonify({"status": "success", "message": "Year updated", "year_id": year.id})

        else:
            # ---- CREATE MODE ----
            new_year = JanmotsavYear(
                year=data["year"],
                is_current=data.get("is_current", False),
                event_name=data.get("event_name"),
                location_name=data.get("location_name"),
                location_url=data.get("location_url"),
                facebook_url=data.get("facebook_url"),
                youtube_url=data.get("youtube_url"),
                instagram_url=data.get("instagram_url"),
                custom_link_1=data.get("custom_link_1"),
                custom_link_2=data.get("custom_link_2"),
                description=data.get("description"),
            )

            db.session.add(new_year)
            db.session.commit()

            return jsonify({"status": "success", "message": "Year created", "year_id": new_year.id})

    except Exception as e:
        db.session.rollback()
        print("Error creating/updating year:", e)
        return jsonify({"error": "Failed to save year"}), 500


# ==========================================================
# ADD DAYS TO YEAR (ADMIN)
# ==========================================================
@router.post("/janmotsav/admin/days/add")
def add_days():
    """Replace old days with the new list for the given year."""
    data = request.json
    year_id = data["year_id"]

    try:
        # DELETE EXISTING DAYS FOR THIS YEAR
        JanmotsavDay.query.filter_by(year_id=year_id).delete()

        # INSERT NEW DAYS
        for d in data["days"]:
            new_day = JanmotsavDay(
                year_id=year_id,
                event_date=datetime.strptime(d["date"], "%Y-%m-%d").date(),
                breakfast=d.get("breakfast", False),
                lunch=d.get("lunch", False),
                evesnacks=d.get("evesnacks", False),
                dinner=d.get("dinner", False),
            )
            db.session.add(new_day)

        db.session.commit()
        return jsonify({"status": "success"})

    except Exception as e:
        db.session.rollback()
        print("Error adding days:", e)
        return jsonify({"error": "Failed to add days"}), 500

# ==========================================================
# ATTENDANCE SUMMARY PER USER
# ==========================================================
@router.get("/janmotsav/attendance/summary/<int:user_id>")
def attendance_summary_user(user_id):
    """Return attendance summary for a user for the current Janmotsav year."""
    year = JanmotsavYear.query.filter_by(is_current=True, is_deleted=False).first()

    if not year:
        return jsonify({"error": "No Janmotsav year found"}), 404

    days = JanmotsavDay.query.filter_by(
        year_id=year.id, is_deleted=False
    ).order_by(JanmotsavDay.event_date).all()

    response = {
        "year": year.year,
        "event_name": year.event_name,
        "days": []
    }

    for day in days:
        att = JanmotsavAttendance.query.filter_by(
            user_id=user_id, day_id=day.id, is_deleted=False
        ).first()

        response["days"].append({
            "dateFormatted": day.event_date.strftime("%d %b"),
            "breakfast": att.breakfast_count if att else 0,
            "lunch": att.lunch_count if att else 0,
            "evesnacks": att.evesnacks_count if att else 0,
            "dinner": att.dinner_count if att else 0,
            "seva_nidhi": att.seva_nidhi if att else False,
        })

    return jsonify(response)

@router.get("/janmotsav/attendance/summary")
def attendance_summary_all():
    """Return attendance summary for all users for the current Janmotsav year."""
    
    year = JanmotsavYear.query.filter_by(
        is_current=True, is_deleted=False
    ).first()

    if not year:
        return jsonify({"error": "No current Janmotsav year found"}), 404

    days = JanmotsavDay.query.filter_by(
        year_id=year.id, is_deleted=False
    ).order_by(JanmotsavDay.event_date).all()

    response = {
        "year": year.year,
        "event_name": year.event_name,
        "days": []
    }

    for day in days:
        totals = db.session.query(
            db.func.sum(JanmotsavAttendance.breakfast_count),
            db.func.sum(JanmotsavAttendance.lunch_count),
            db.func.sum(JanmotsavAttendance.evesnacks_count),
            db.func.sum(JanmotsavAttendance.dinner_count),
            db.func.bool_or(JanmotsavAttendance.seva_nidhi)
        ).filter_by(day_id=day.id, is_deleted=False).first()

        response["days"].append({
            "date": day.event_date.strftime("%Y-%m-%d"),
            "dateFormatted": day.event_date.strftime("%d %b"),
            "breakfast_total": totals[0] or 0,
            "lunch_total": totals[1] or 0,
            "evesnacks_total": totals[2] or 0,
            "dinner_total": totals[3] or 0,
            "seva_nidhi_any": totals[4] or False,
        })

    return jsonify(response)


# ==========================================================
# LIST ALL YEARS (ADMIN)
# ==========================================================
@router.get("/janmotsav/admin/year/list")
def list_years():
    """Return all active (non-deleted) Janmotsav years."""
    years = (
        JanmotsavYear.query
            .filter_by(is_deleted=False)
            .order_by(JanmotsavYear.year.desc())
            .all()
    )

    return jsonify({
        "years": [
            {
                "id": y.id,
                "year": y.year,
                "event_name": y.event_name,
                "is_current": y.is_current
            }
            for y in years
        ]
    })


# ==========================================================
# GET YEAR DETAILS FOR EDITING (ADMIN)
# ==========================================================
@router.get("/janmotsav/admin/year/<int:year_id>")
def get_year_details(year_id):
    """Return full details of selected Janmotsav year for Admin edit."""
    year = JanmotsavYear.query.filter_by(id=year_id, is_deleted=False).first()

    if not year:
        return jsonify({"error": "Year not found"}), 404

    days = (
        JanmotsavDay.query
            .filter_by(year_id=year_id, is_deleted=False)
            .order_by(JanmotsavDay.event_date)
            .all()
    )

    return jsonify({
        "id": year.id,
        "year": year.year,
        "event_name": year.event_name,
        "is_current": year.is_current,
        "location_name": year.location_name,
        "location_url": year.location_url,
        "facebook_url": year.facebook_url,
        "youtube_url": year.youtube_url,
        "instagram_url": year.instagram_url,
        "custom_link_1": year.custom_link_1,
        "custom_link_2": year.custom_link_2,
        "description": year.description,
        "days": [
            {
                "id": d.id,
                "date": d.event_date.isoformat(),
                "breakfast": d.breakfast,
                "lunch": d.lunch,
                "evesnacks": d.evesnacks,
                "dinner": d.dinner,
            }
            for d in days
        ]
    })


# ==========================================================
# SOFT DELETE YEAR
# ==========================================================
@router.delete("/janmotsav/admin/year/delete/<int:year_id>")
def delete_year(year_id):
    """Soft delete a year."""
    year = JanmotsavYear.query.filter_by(id=year_id, is_deleted=False).first()

    if not year:
        return jsonify({"error": "Year not found"}), 404

    try:
        year.is_deleted = True
        db.session.commit()
        return jsonify({"status": "success"})

    except Exception as e:
        db.session.rollback()
        print("Error deleting year:", e)
        return jsonify({"error": "Failed to delete year"}), 500
