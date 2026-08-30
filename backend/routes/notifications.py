from flask import Blueprint, session, jsonify
from services.notification_service import get_notifications
from routes.decorators import login_required

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/api/notifications", methods=["GET"])
@login_required()
def notifications():
    role = session["role"]
    if role == "student":
        rows = get_notifications("student", student_id=session.get("student_id"))
    else:
        rows = get_notifications("admin")
    return jsonify({"success": True, "notifications": rows})
