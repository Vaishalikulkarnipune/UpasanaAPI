from flask import Blueprint, request, jsonify
from datetime import datetime
from model import (
    db,
    JanmotsavYear,
    JanmotsavDay,
    JanmotsavAttendance,
    SevaNidhiPayment
)

router = Blueprint("janmotsav", __name__)

# ==========================================================
# GET CURRENT CONFIG
# ==========================================================
@router.get("/janmotsav/config/current")
def get_current_config():
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

        # LOCATION + SOCIAL LINKS
        "location_name": year.location_name,
        "location_url": year.location_url,
        "facebook_url": year.facebook_url,
        "youtube_url": year.youtube_url,
        "instagram_url": year.instagram_url,

        # CUSTOM
        "custom_link_1": year.custom_link_1,
        "custom_link_2": year.custom_link_2,

        "description": year.description,

        # NEW EVENT FLAGS
        "enable_payment_flag": year.enable_payment_flag,
        "is_event_closed": year.is_event_closed,

        # DAYS LIST
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
# SAVE ATTENDANCE + SEVA NIDHI
# ==========================================================
@router.post("/janmotsav/attendance/save")
def save_attendance():
    data = request.json

    user_id = data["user_id"]
    year_id = data["year_id"]

    seva_nidhi = data.get("seva_nidhi", False)
    seva_nidhi_amount = data.get("seva_nidhi_amount")
    seva_nidhi_account_details = data.get("seva_nidhi_account_details")

    try:
        # ------------------------------------------------------
        # 1️⃣ SAVE / UPDATE SEVA NIDHI PAYMENT
        # ------------------------------------------------------
        if seva_nidhi:
            # Check if a record already exists for the same user + year
            existing_payment = SevaNidhiPayment.query.filter_by(
                user_id=user_id,
                year_id=year_id
            ).first()

            if existing_payment:
                # Update existing entry
                existing_payment.amount = seva_nidhi_amount
                existing_payment.account_details = seva_nidhi_account_details
                existing_payment.updated_at = datetime.utcnow()
            else:
                # Create new entry
                new_payment = SevaNidhiPayment(
                    user_id=user_id,
                    year_id=year_id,
                    amount=seva_nidhi_amount,
                    account_details=seva_nidhi_account_details,
                )
                db.session.add(new_payment)

        # ------------------------------------------------------
        # 2️⃣ SAVE ATTENDANCE (PER DAY)
        # ------------------------------------------------------
        for entry in data["attendance"]:
            day_id = entry["day_id"]

            existing = JanmotsavAttendance.query.filter_by(
                user_id=user_id,
                year_id=year_id,
                day_id=day_id,
                is_deleted=False
            ).first()

            if existing:
                existing.breakfast_count = entry.get("breakfast", 0)
                existing.lunch_count = entry.get("lunch", 0)
                existing.evesnacks_count = entry.get("evesnacks", 0)
                existing.dinner_count = entry.get("dinner", 0)
                existing.updated_at = datetime.utcnow()
            else:
                rec = JanmotsavAttendance(
                    user_id=user_id,
                    year_id=year_id,
                    day_id=day_id,
                    breakfast_count=entry.get("breakfast", 0),
                    lunch_count=entry.get("lunch", 0),
                    evesnacks_count=entry.get("evesnacks", 0),
                    dinner_count=entry.get("dinner", 0),
                )
                db.session.add(rec)

        db.session.commit()
        return jsonify({"status": "success"})

    except Exception as e:
        db.session.rollback()
        print("Error saving attendance:", e)
        return jsonify({"error": "Failed to save attendance"}), 500

# ==========================================================
# ADMIN: CREATE / UPDATE YEAR
# ==========================================================
@router.post("/janmotsav/admin/year/create")
def create_or_update_year():
    data = request.json
    year_id = data.get("id")

    try:
        if data.get("is_current"):
            JanmotsavYear.query.update({"is_current": False})

        if year_id:
            year = JanmotsavYear.query.get(year_id)
            if not year:
                return jsonify({"error": "Year not found"}), 404

            # Update fields
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
# ADMIN: ADD DAYS TO YEAR
# ==========================================================
@router.post("/janmotsav/admin/days/add")
def add_days():
    data = request.json
    year_id = data["year_id"]

    try:
        JanmotsavDay.query.filter_by(year_id=year_id).update({"is_deleted": True})

        for d in data["days"]:
            new_day = JanmotsavDay(
                year_id=year_id,
                event_date=datetime.strptime(d["date"], "%Y-%m-%d").date(),
                breakfast=d.get("breakfast", False),
                lunch=d.get("lunch", False),
                evesnacks=d.get("evesnacks", False),
                dinner=d.get("dinner", False),
                is_deleted=False
            )
            db.session.add(new_day)

        db.session.commit()
        return jsonify({"status": "success"})

    except Exception as e:
        db.session.rollback()
        print("Error adding days:", e)
        return jsonify({"error": "Failed to add days"}), 500

# ==========================================================
# USER ATTENDANCE SUMMARY
# ==========================================================
@router.get("/janmotsav/attendance/summary/<int:user_id>")
def attendance_summary_user(user_id):
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

    # ============================================================
    # FETCH SEVA NIDHI PAYMENTS (NEW + FIXED)
    # ============================================================
    payments = SevaNidhiPayment.query.filter_by(
        user_id=user_id,
        year_id=year.id
    ).order_by(SevaNidhiPayment.created_at.asc()).all()

    total_paid = sum(p.amount for p in payments)
    last_payment = payments[-1] if payments else None

    response["seva_nidhi_paid"] = len(payments) > 0
    response["seva_nidhi_total_amount"] = total_paid
    response["seva_nidhi_account_details"] = (
        last_payment.account_details if last_payment else None
    )

    # ============================================================
    # ATTENDANCE FOR EACH DAY
    # ============================================================
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
        })

    return jsonify(response)

# ==========================================================
# ALL USERS SUMMARY (ADMIN) - FIXED
# ==========================================================
@router.get("/janmotsav/attendance/summary")
def attendance_summary_all():
    year = JanmotsavYear.query.filter_by(
        is_current=True, is_deleted=False
    ).first()

    if not year:
        return jsonify({"error": "No current Janmotsav year found"}), 404

    rows = (
        db.session.query(
            JanmotsavDay.event_date,
            db.func.sum(JanmotsavAttendance.breakfast_count),
            db.func.sum(JanmotsavAttendance.lunch_count),
            db.func.sum(JanmotsavAttendance.evesnacks_count),
            db.func.sum(JanmotsavAttendance.dinner_count),
        )
        .join(JanmotsavDay, JanmotsavDay.id == JanmotsavAttendance.day_id)
        .filter(
            JanmotsavAttendance.year_id == year.id,
            JanmotsavAttendance.is_deleted == False,
            JanmotsavDay.is_deleted == False,
        )
        .group_by(JanmotsavDay.event_date)
        .order_by(JanmotsavDay.event_date)
        .all()
    )

    response = {
        "year": year.year,
        "event_name": year.event_name,
        "days": [],
    }

    for row in rows:
        response["days"].append({
            "date": row[0].strftime("%Y-%m-%d"),
            "dateFormatted": row[0].strftime("%d %b"),
            "breakfast_total": row[1] or 0,
            "lunch_total": row[2] or 0,
            "evesnacks_total": row[3] or 0,
            "dinner_total": row[4] or 0,
        })

    # Seva Nidhi total
    response["seva_nidhi_total"] = (
        db.session.query(db.func.coalesce(db.func.sum(SevaNidhiPayment.amount), 0))
        .filter(SevaNidhiPayment.year_id == year.id)
        .scalar()
    )

    return jsonify(response)

# ==========================================================
# LIST YEARS (ADMIN)
# ==========================================================
@router.get("/janmotsav/admin/year/list")
def list_years():
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
# GET YEAR DETAILS (ADMIN)
# ==========================================================
@router.get("/janmotsav/admin/year/<int:year_id>")
def get_year_details(year_id):
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
# DELETE YEAR (SOFT DELETE)
# ==========================================================
@router.delete("/janmotsav/admin/year/delete/<int:year_id>")
def delete_year(year_id):
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
