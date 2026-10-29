"""
Day notes (विशेष दिवस): festivals / tithis on Upasana dates — एकादशी, संकष्ट चतुर्थी (चंद्रोदय …),
महाशिवरात्री … — kept per date so they can be added for every year.

Members see the Saturday ones while booking and on their own Upasana; admins see every day
(Sundays included) when they give a date.

  GET    /day-notes?from=YYYY-MM-DD          public: [{date, title_mr, title_en}] from that date (default: 1 Jan this year)
  POST   /admin/day-notes                    admin:  { date, title_mr, title_en? }   (adds or changes one day)
  DELETE /admin/day-notes/<YYYY-MM-DD>       admin

The table is created when the API starts, with the 2027 list (also migrations/add_day_notes.sql);
add later years with the same INSERT pattern or the admin endpoint.
"""
import logging
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from admin_auth import require_admin
from model import db
import schema_check

router = Blueprint("day_notes", __name__)

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS upasana_day_notes (
           note_date DATE PRIMARY KEY,
           title_mr VARCHAR(200) NOT NULL,
           title_en VARCHAR(200),
           updated_at TIMESTAMP,
           updated_by VARCHAR(120)
       )""",
    # 2027 (only days not there yet)
    """INSERT INTO upasana_day_notes (note_date, title_mr, title_en) VALUES
           ('2027-01-03', 'एकादशी', 'Ekadashi'),
           ('2027-02-27', 'श्री गजानन महाराज प्रकट दिन', 'Shri Gajanan Maharaj Pragat Din'),
           ('2027-03-06', 'महाशिवरात्री', 'Mahashivratri'),
           ('2027-03-21', 'होळी', 'Holi'),
           ('2027-03-27', 'रंगपंचमी', 'Rangpanchami'),
           ('2027-04-24', 'संकष्ट चतुर्थी (चंद्रोदय १०:१७)', 'Sankashti Chaturthi (moonrise 10:17)'),
           ('2027-05-02', 'एकादशी', 'Ekadashi'),
           ('2027-05-16', 'एकादशी', 'Ekadashi'),
           ('2027-05-23', 'संकष्ट चतुर्थी (चंद्रोदय ९:५०)', 'Sankashti Chaturthi (moonrise 9:50)'),
           ('2027-07-18', 'गुरुपौर्णिमा', 'Guru Pournima'),
           ('2027-08-28', 'एकादशी', 'Ekadashi'),
           ('2027-09-04', 'श्री गणेश चतुर्थी, ऋषिपंचमी', 'Shri Ganesh Chaturthi, Rushipanchami'),
           ('2027-09-11', 'एकादशी', 'Ekadashi'),
           ('2027-09-19', 'संकष्ट चतुर्थी (चंद्रोदय ८:३६)', 'Sankashti Chaturthi (moonrise 8:36)'),
           ('2027-09-26', 'एकादशी', 'Ekadashi'),
           ('2027-10-09', 'दसरा', 'Dasara'),
           ('2027-10-30', 'बलिप्रतिपदा, दिवाळी पाडवा', 'Balipratipada, Diwali Padwa'),
           ('2027-10-31', 'भाऊबीज', 'Bhaubij')
       ON CONFLICT (note_date) DO NOTHING""",
]


def ready():
    return schema_check.has("upasana_day_notes.note_date")


def _row(r):
    return {"date": r[0].strftime("%Y-%m-%d"), "title_mr": r[1], "title_en": r[2] or ""}


@router.route("/day-notes", methods=["GET"])
def list_day_notes():
    if not ready():
        return jsonify({"notes": [], "available": False}), 200
    try:
        start = datetime.strptime(request.args.get("from", ""), "%Y-%m-%d").date()
    except ValueError:
        start = date(date.today().year, 1, 1)
    rows = db.session.execute(
        text("SELECT note_date, title_mr, title_en FROM upasana_day_notes WHERE note_date >= :d ORDER BY note_date"),
        {"d": start},
    ).all()
    return jsonify({"notes": [_row(r) for r in rows], "available": True}), 200


@router.route("/admin/day-notes", methods=["POST"])
def save_day_note():
    err, status, admin_label = require_admin()
    if err:
        return err, status
    if not ready():
        return jsonify({"error": "Day notes are not available yet."}), 503
    data = request.get_json(silent=True) or {}
    try:
        day = datetime.strptime(str(data.get("date", "")), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Date must be YYYY-MM-DD."}), 400
    title_mr = str(data.get("title_mr", "")).strip()[:200]
    title_en = str(data.get("title_en", "") or "").strip()[:200]
    if not title_mr:
        return jsonify({"error": "Enter the Marathi name of the day."}), 400
    db.session.execute(
        text("""INSERT INTO upasana_day_notes (note_date, title_mr, title_en, updated_at, updated_by)
                VALUES (:d, :mr, NULLIF(:en, ''), NOW() AT TIME ZONE 'Asia/Kolkata', :by)
                ON CONFLICT (note_date) DO UPDATE SET title_mr = :mr, title_en = NULLIF(:en, ''),
                  updated_at = NOW() AT TIME ZONE 'Asia/Kolkata', updated_by = :by"""),
        {"d": day, "mr": title_mr, "en": title_en, "by": (admin_label or "")[:120]},
    )
    db.session.commit()
    logging.info(f"Admin {admin_label} saved day note {day}")
    return jsonify({"message": "Saved.", "note": {"date": day.strftime("%Y-%m-%d"), "title_mr": title_mr, "title_en": title_en}}), 200


@router.route("/admin/day-notes/<day>", methods=["DELETE"])
def delete_day_note(day):
    err, status, admin_label = require_admin()
    if err:
        return err, status
    if not ready():
        return jsonify({"error": "Day notes are not available yet."}), 503
    n = db.session.execute(text("DELETE FROM upasana_day_notes WHERE note_date = :d"), {"d": day}).rowcount
    db.session.commit()
    logging.info(f"Admin {admin_label} removed day note {day}")
    return jsonify({"message": "Removed." if n else "No note on this day."}), 200
