import io
from datetime import date, datetime

from flask import Blueprint, request, jsonify, send_file, session
import qrcode

from database import run_query
from routes.decorators import login_required
from services.notification_service import create_notification

attendance_bp = Blueprint("attendance", __name__)


def _qr_code_for_bus(bus_id):
    """QR payload format: BUS-<bus_id>-<YYYYMMDD>. Simple and easy to explain,
    unique per bus per day so an old QR image can't be reused on another day."""
    return f"BUS-{bus_id}-{date.today().strftime('%Y%m%d')}"


@attendance_bp.route("/api/buses/<int:bus_id>/qr", methods=["GET"])
@login_required()
def get_bus_qr(bus_id):
    """Returns a PNG QR code image for the given bus, valid for today.
    In real deployment this would be printed/displayed at the bus door."""
    payload = _qr_code_for_bus(bus_id)
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@attendance_bp.route("/api/buses/<int:bus_id>/qr-code-text", methods=["GET"])
@login_required()
def get_bus_qr_text(bus_id):
    """Fallback/demo mode: returns the raw QR text so it can be typed in
    manually if camera scanning is unavailable in the dev environment."""
    return jsonify({"success": True, "qr_text": _qr_code_for_bus(bus_id)})


@attendance_bp.route("/api/boarding", methods=["POST"])
@login_required("student")
def board_bus():
    data = request.get_json(force=True) or {}
    scanned_text = data.get("qr_text", "").strip()
    student_id = session["student_id"]

    parts = scanned_text.split("-")
    if len(parts) != 3 or parts[0] != "BUS":
        return jsonify({"success": False, "message": "Invalid QR code"}), 400

    try:
        bus_id = int(parts[1])
        qr_date = parts[2]
    except ValueError:
        return jsonify({"success": False, "message": "Invalid QR code"}), 400

    if qr_date != date.today().strftime("%Y%m%d"):
        return jsonify({"success": False, "message": "This QR code has expired (not for today)"}), 400

    assignment = run_query(
        "SELECT * FROM student_bus_assignments WHERE student_id=%s AND bus_id=%s",
        (student_id, bus_id), fetch_one=True,
    )
    if not assignment:
        return jsonify({"success": False, "message": "This is not your assigned bus"}), 403

    # Prevent duplicate boarding for the same student/bus/day
    existing = run_query(
        "SELECT * FROM attendance WHERE student_id=%s AND bus_id=%s AND attendance_date=%s",
        (student_id, bus_id, date.today()), fetch_one=True,
    )
    if existing:
        return jsonify({"success": False, "message": "Attendance already recorded for today"}), 409

    bus = run_query("SELECT * FROM buses WHERE id=%s", (bus_id,), fetch_one=True)
    if bus["current_passengers"] >= bus["capacity"]:
        return jsonify({"success": False, "message": "Bus Full - Boarding Not Available"}), 400

    now = datetime.now()
    run_query(
        """INSERT INTO attendance (student_id, bus_id, stop_id, attendance_date, attendance_time, boarding_status)
           VALUES (%s,%s,%s,%s,%s,'boarded')""",
        (student_id, bus_id, assignment["stop_id"], date.today(), now.strftime("%H:%M:%S")),
        commit=True,
    )
    run_query("UPDATE buses SET current_passengers = current_passengers + 1 WHERE id=%s", (bus_id,), commit=True)

    updated_bus = run_query("SELECT * FROM buses WHERE id=%s", (bus_id,), fetch_one=True)
    student = run_query("SELECT * FROM students WHERE id=%s", (student_id,), fetch_one=True)

    create_notification(
        "student", "Boarding confirmed. Attendance recorded successfully.", "boarding_confirmed",
        bus_id=bus_id, student_id=student_id,
    )
    create_notification(
        "admin", f"{student['name']} boarded {bus['bus_name']}.", "boarding_confirmed", bus_id=bus_id,
    )

    if updated_bus["current_passengers"] >= updated_bus["capacity"]:
        create_notification("admin", f"{bus['bus_name']} has reached full capacity.", "capacity_warning", bus_id=bus_id)

    return jsonify({
        "success": True,
        "message": "Boarding confirmed",
        "passengers": updated_bus["current_passengers"],
        "capacity": updated_bus["capacity"],
        "available_seats": updated_bus["capacity"] - updated_bus["current_passengers"],
    })


@attendance_bp.route("/api/attendance", methods=["GET"])
@login_required("admin")
def list_attendance():
    bus_id = request.args.get("bus_id", type=int)
    query = """SELECT a.*, s.name AS student_name, bs.stop_name, b.bus_name
               FROM attendance a
               JOIN students s ON s.id = a.student_id
               JOIN bus_stops bs ON bs.id = a.stop_id
               JOIN buses b ON b.id = a.bus_id
               WHERE a.attendance_date = CURDATE()"""
    params = ()
    if bus_id:
        query += " AND a.bus_id=%s"
        params = (bus_id,)
    query += " ORDER BY a.attendance_time DESC"
    rows = run_query(query, params, fetch=True)
    # mysql-connector returns TIME columns as timedelta, which isn't JSON
    # serializable - convert to a plain "HH:MM:SS" string for the API.
    for r in rows:
        if r.get("attendance_time") is not None:
            r["attendance_time"] = str(r["attendance_time"])
        if r.get("attendance_date") is not None:
            r["attendance_date"] = str(r["attendance_date"])
    return jsonify({"success": True, "attendance": rows})
