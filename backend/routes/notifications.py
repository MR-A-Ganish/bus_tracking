from flask import Blueprint, jsonify, session

from database import run_query
from routes.decorators import login_required


notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/api/notifications", methods=["GET"])
@login_required()
def list_notifications():
    role = session["role"]
    if role == "student":
        rows = run_query(
            """SELECT * FROM notifications
               WHERE target_role IN ('all', 'student')
                 AND (student_id IS NULL OR student_id=%s)
                 AND (bus_id IS NULL OR bus_id IN (SELECT bus_id FROM student_bus_assignments WHERE student_id=%s))
               ORDER BY created_at DESC LIMIT 30""",
            (session["student_id"],session["student_id"]), fetch=True,
        )
    elif role == "admin":
        rows = run_query(
            """SELECT * FROM notifications
               WHERE target_role IN ('all', 'admin')
               ORDER BY created_at DESC LIMIT 30""",
            fetch=True,
        )
    else:
        rows = run_query(
            "SELECT * FROM notifications WHERE target_role='all' ORDER BY created_at DESC LIMIT 30",
            fetch=True,
        )
    return jsonify({"success": True, "notifications": rows})
