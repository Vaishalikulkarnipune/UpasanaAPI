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
# ⚠️ LEGACY API
# Used by old mobile app (expects day_id)
# DO NOT MODIFY
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
        # 1️⃣ SEVA NIDHI (SAFE)
        # ------------------------------------------------------
        if seva_nidhi:
            payment = SevaNidhiPayment.query.filter_by(
                user_id=user_id,
                year_id=year_id
            ).first()

            if payment:
                payment.amount = seva_nidhi_amount
                payment.account_details = seva_nidhi_account_details
                payment.updated_at = datetime.utcnow()
            else:
                db.session.add(
                    SevaNidhiPayment(
                        user_id=user_id,
                        year_id=year_id,
                        amount=seva_nidhi_amount,
                        account_details=seva_nidhi_account_details
                    )
                )

        # ------------------------------------------------------
        # 2️⃣ ATTENDANCE (FIXED – DAY RESOLUTION)
        # ------------------------------------------------------
        for entry in data["attendance"]:
            event_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()

            # 🔒 Resolve correct day (ONLY ONE ALLOWED)
            day = JanmotsavDay.query.filter_by(
                year_id=year_id,
                event_date=event_date,
                is_deleted=False
            ).first()

            if not day:
                continue  # or raise error if strict

            existing = JanmotsavAttendance.query.filter_by(
                user_id=user_id,
                year_id=year_id,
                day_id=day.id,
                is_deleted=False
            ).first()

            if existing:
                existing.breakfast_count = entry.get("breakfast", 0)
                existing.lunch_count = entry.get("lunch", 0)
                existing.evesnacks_count = entry.get("evesnacks", 0)
                existing.dinner_count = entry.get("dinner", 0)
                existing.updated_at = datetime.utcnow()
            else:
                db.session.add(
                    JanmotsavAttendance(
                        user_id=user_id,
                        year_id=year_id,
                        day_id=day.id,
                        breakfast_count=entry.get("breakfast", 0),
                        lunch_count=entry.get("lunch", 0),
                        evesnacks_count=entry.get("evesnacks", 0),
                        dinner_count=entry.get("dinner", 0),
                    )
                )

        db.session.commit()
        return jsonify({"status": "success"})

    except Exception as e:
        db.session.rollback()
        print("Error saving attendance:", e)
        return jsonify({"error": "Failed to save attendance"}), 500
    
# ==========================================================
# SAVE ATTENDANCE + SEVA NIDHI
# ==========================================================
@router.post("/janmotsav/attendance/v1/save")
def save_attendance_v1():
    print("========== SAVE ATTENDANCE API CALLED ==========")

    data = request.json
    print("📥 Incoming JSON:", data)

    try:
        user_id = data["user_id"]
        year_id = data["year_id"]
        print(f"👤 user_id={user_id}, 📅 year_id={year_id}")

        seva_nidhi = data.get("seva_nidhi", False)
        seva_nidhi_amount = data.get("seva_nidhi_amount")
        seva_nidhi_account_details = data.get("seva_nidhi_account_details")

        print(
            f"💰 seva_nidhi={seva_nidhi}, "
            f"amount={seva_nidhi_amount}, "
            f"account={seva_nidhi_account_details}"
        )

        # ------------------------------------------------------
        # 1️⃣ SEVA NIDHI
        # ------------------------------------------------------
        if seva_nidhi:
            print("➡️ Processing Seva Nidhi")

            payment = SevaNidhiPayment.query.filter_by(
                user_id=user_id,
                year_id=year_id
            ).first()

            if payment:
                print("🔁 Existing Seva Nidhi record found, updating")
                payment.amount = seva_nidhi_amount
                payment.account_details = seva_nidhi_account_details
                payment.updated_at = datetime.utcnow()
            else:
                print("➕ Creating new Seva Nidhi record")
                db.session.add(
                    SevaNidhiPayment(
                        user_id=user_id,
                        year_id=year_id,
                        amount=seva_nidhi_amount,
                        account_details=seva_nidhi_account_details
                    )
                )
        else:
            print("ℹ️ Seva Nidhi not provided, skipping")

        # ------------------------------------------------------
        # 2️⃣ ATTENDANCE
        # ------------------------------------------------------
        attendance_list = data.get("attendance", [])
        print(f"📋 Attendance entries received: {len(attendance_list)}")

        for idx, entry in enumerate(attendance_list):
            print(f"➡️ Processing attendance index {idx}: {entry}")

            if "date" not in entry:
                print("❌ Missing 'date' in entry, skipping")
                continue

            try:
                event_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
                print(f"📆 Parsed event_date={event_date}")
            except Exception as e:
                print("❌ Date parsing failed:", e)
                continue

            day = JanmotsavDay.query.filter_by(
                year_id=year_id,
                event_date=event_date,
                is_deleted=False
            ).first()

            if not day:
                print(f"⚠️ No JanmotsavDay found for date {event_date}, skipping")
                continue

            print(f"✅ Resolved day_id={day.id}")

            existing = JanmotsavAttendance.query.filter_by(
                user_id=user_id,
                year_id=year_id,
                day_id=day.id,
                is_deleted=False
            ).first()

            if existing:
                print("🔁 Existing attendance found, updating")
                existing.breakfast_count = entry.get("breakfast", 0)
                existing.lunch_count = entry.get("lunch", 0)
                existing.evesnacks_count = entry.get("evesnacks", 0)
                existing.dinner_count = entry.get("dinner", 0)
                existing.updated_at = datetime.utcnow()
            else:
                print("➕ Creating new attendance record")
                db.session.add(
                    JanmotsavAttendance(
                        user_id=user_id,
                        year_id=year_id,
                        day_id=day.id,
                        breakfast_count=entry.get("breakfast", 0),
                        lunch_count=entry.get("lunch", 0),
                        evesnacks_count=entry.get("evesnacks", 0),
                        dinner_count=entry.get("dinner", 0),
                    )
                )

        print("💾 Committing DB transaction")
        db.session.commit()

        print("✅ SAVE ATTENDANCE SUCCESS")
        return jsonify({"status": "success"})

    except Exception as e:
        print("🔥 ERROR in save_attendance:", str(e))
        db.session.rollback()
        print("↩️ DB ROLLBACK DONE")
        return jsonify({"error": "Failed to save attendance"}), 500


# ==========================================================
# ADMIN: CREATE / UPDATE YEAR (MAINTENANCE)
# ==========================================================
@router.post("/janmotsav/admin/year/create")
def create_or_update_year():
    return jsonify({
        "status": "error",
        "message": "This API is under maintenance. Please try again later."
    }), 503


# ==========================================================
# ADMIN: ADD DAYS TO YEAR (MAINTENANCE)
# ==========================================================
@router.post("/janmotsav/admin/days/add")
def add_days():
    return jsonify({
        "status": "error",
        "message": "This API is under maintenance. Please try again later."
    }), 503
# ==========================================================
# ADMIN: CREATE / UPDATE YEAR
# ==========================================================
@router.post("/janmotsav/admin/year/createOLD")
def create_or_update_year_old():
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
@router.post("/janmotsav/admin/days/addOLD")
def add_days_old():
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
# ALL USERS SUMMARY (ADMIN)
# ==========================================================
@router.get("/janmotsav/attendance/summary")
def attendance_summary_all():
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
        ).filter_by(day_id=day.id, is_deleted=False).first()

        response["days"].append({
            "date": day.event_date.strftime("%Y-%m-%d"),
            "dateFormatted": day.event_date.strftime("%d %b"),
            "breakfast_total": totals[0] or 0,
            "lunch_total": totals[1] or 0,
            "evesnacks_total": totals[2] or 0,
            "dinner_total": totals[3] or 0,
        })

    # Add seva-nidhi totals (NEW)
    all_payments = SevaNidhiPayment.query.filter_by(year_id=year.id).all()
    response["seva_nidhi_total"] = sum(p.amount for p in all_payments)

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
