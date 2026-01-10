from flask import Blueprint, request, jsonify
from datetime import datetime
from model import db, JanmotsavYear, JanmotsavDay, JanmotsavAttendance

router = Blueprint("janmotsav", __name__)

# ---------------------------------------------------------
# GET CURRENT CONFIG
# ---------------------------------------------------------
@router.get("/janmotsav/config/current")
def get_current_config():
    print("Fetching current Janmotsav configuration")

    year = JanmotsavYear.query.filter_by(is_current=True).first()

    if not year:
        print("No current Janmotsav year found")
        return jsonify({"error": "No current Janmotsav year set"}), 200

    days = (
        JanmotsavDay.query
        .filter_by(year_id=year.id)
        .order_by(JanmotsavDay.event_date)
        .all()
    )

    print(f"Loaded Janmotsav year={year.year}, days={len(days)}")

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


# ---------------------------------------------------------
# SAVE ATTENDANCE
# ---------------------------------------------------------
@router.post("/janmotsav/attendance/save")
def save_attendance():
    data = request.json
    print(f"Saving attendance for user {data.get('user_id')}")

    user_id = data["user_id"]
    year_id = data["year_id"]

    try:
        for entry in data["attendance"]:
            day_id = entry["day_id"]
            print(f"Processing: user={user_id}, day={day_id}")

            existing = JanmotsavAttendance.query.filter_by(
                user_id=user_id,
                year_id=year_id,
                day_id=day_id
            ).first()

            if existing:
                print(f"Updating existing attendance user={user_id}, day={day_id}")
                existing.breakfast_count = entry.get("breakfast", 0)
                existing.lunch_count = entry.get("lunch", 0)
                existing.evesnacks_count = entry.get("evesnacks", 0)
                existing.dinner_count = entry.get("dinner", 0)
                existing.seva_nidhi = entry.get("seva_nidhi", False)
                existing.updated_at = datetime.utcnow()
            else:
                print(f"Creating new attendance record user={user_id}, day={day_id}")
                new_rec = JanmotsavAttendance(
                    user_id=user_id,
                    year_id=year_id,
                    day_id=day_id,
                    breakfast_count=entry.get("breakfast", 0),
                    lunch_count=entry.get("lunch", 0),
                    evesnacks_count=entry.get("evesnacks", 0),
                    dinner_count=entry.get("dinner", 0),
                    seva_nidhi=entry.get("seva_nidhi", False),
                )
                db.session.add(new_rec)

        db.session.commit()
        print("Attendance saved successfully")
        return jsonify({"status": "success"})

    except Exception as e:
        print(f"Error saving attendance: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to save attendance"}), 500


# ---------------------------------------------------------
# CREATE YEAR (ADMIN)
# ---------------------------------------------------------
@router.post("/janmotsav/admin/year/create")
def create_year():
    data = request.json
    print(f"Admin creating Janmotsav year {data.get('year')}")

    try:
        if data.get("is_current"):
            print("Setting previous years is_current=False")
            JanmotsavYear.query.update({"is_current": False})

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

        print(f"Created year successfully: ID={new_year.id}")
        return jsonify({"status": "success", "year_id": new_year.id})

    except Exception as e:
        print(f"Error creating year: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to create year"}), 500


# ---------------------------------------------------------
# ADD DAYS (ADMIN)
# ---------------------------------------------------------
@router.post("/janmotsav/admin/days/add")
def add_days():
    data = request.json
    year_id = data["year_id"]

    print(f"Adding days for year_id={year_id}")

    try:
        for d in data["days"]:
            print(f"Adding day: {d}")
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
        print("Days added")
        return jsonify({"status": "success"})

    except Exception as e:
        print(f"Error adding days: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to add days"}), 500


# ---------------------------------------------------------
# ATTENDANCE SUMMARY
# ---------------------------------------------------------
@router.get("/janmotsav/attendance/summary/<int:user_id>")
def attendance_summary(user_id):
    print(f"Fetching summary for user={user_id}")

    year = JanmotsavYear.query.filter_by(is_current=True).first()

    if not year:
        print("No Janmotsav year found")
        return jsonify({"error": "No Janmotsav year found"}), 404

    days = (
        JanmotsavDay.query
        .filter_by(year_id=year.id)
        .order_by(JanmotsavDay.event_date)
        .all()
    )

    response = {
        "year": year.year,
        "event_name": year.event_name,
        "days": []
    }

    for day in days:
        att = JanmotsavAttendance.query.filter_by(
            user_id=user_id,
            day_id=day.id
        ).first()

        print(f"Day={day.id}, attendance={'found' if att else 'none'}")

        response["days"].append({
            "dateFormatted": day.event_date.strftime("%d %b"),
            "breakfast": att.breakfast_count if att else 0,
            "lunch": att.lunch_count if att else 0,
            "evesnacks": att.evesnacks_count if att else 0,
            "dinner": att.dinner_count if att else 0,
            "seva_nidhi": att.seva_nidhi if att else False,
        })

    return jsonify(response)

    # ---------------------------------------------------------
# LIST ALL YEARS (ADMIN)
# ---------------------------------------------------------
@router.get("/janmotsav/admin/year/list")
def list_years():
    try:
        years = JanmotsavYear.query.filter_by(is_deleted=False).order_by(JanmotsavYear.year.desc()).all()

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

    except Exception as e:
        print("Error loading year list:", e)
        return jsonify({"error": "Failed to load year list"}), 500


# ---------------------------------------------------------
# GET YEAR DETAILS (ADMIN)
# ---------------------------------------------------------
@router.get("/janmotsav/admin/year/<int:year_id>")
def get_year_details(year_id):
    try:
        year = JanmotsavYear.query.filter_by(id=year_id, is_deleted=False).first()

        if not year:
            return jsonify({"error": "Year not found"}), 404

        days = JanmotsavDay.query.filter_by(year_id=year_id, is_deleted=False).order_by(JanmotsavDay.event_date).all()

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
                    "dinner": d.dinner
                }
                for d in days
            ]
        })

    except Exception as e:
        print("Error getting year details:", e)
        return jsonify({"error": "Failed to load year details"}), 500

@router.delete("/janmotsav/admin/year/delete/<int:year_id>")
def delete_year(year_id):
    try:
        year = JanmotsavYear.query.filter_by(id=year_id, is_deleted=False).first()
        if not year:
            return jsonify({"error": "Year not found"}), 404

        year.is_deleted = True
        db.session.commit()

        return jsonify({"status": "success"})

    except Exception as e:
        print("Error deleting year:", e)
        db.session.rollback()
        return jsonify({"error": "Failed to delete year"}), 500