from flask import Blueprint, session, jsonify
from database import run_query
from routes.decorators import login_required

students_bp = Blueprint("students", __name__)


@students_bp.route("/api/students/me", methods=["GET"])
@login_required("student")
def my_profile():
    student_id = session["student_id"]
    student = run_query("SELECT * FROM students WHERE id=%s", (student_id,), fetch_one=True)

    assignment = run_query(
        """SELECT sba.*, b.bus_name, b.capacity, b.current_passengers, bs.stop_name, bs.id AS stop_id,
                  bs.distance_from_start_km, b.id AS bus_id, b.route_id
           FROM student_bus_assignments sba
           JOIN buses b ON b.id = sba.bus_id
           JOIN bus_stops bs ON bs.id = sba.stop_id
           WHERE sba.student_id=%s""",
        (student_id,), fetch_one=True,
    )

    if not assignment:
        return jsonify({"success": True, "student": student, "assignment": None})

    return jsonify({
        "success": True,
        "student": {"id": student["id"], "name": student["name"], "register_no": student["register_no"]},
        "assignment": {
            "bus_id": assignment["bus_id"],
            "bus_name": assignment["bus_name"],
            "capacity": assignment["capacity"],
            "current_passengers": assignment["current_passengers"],
            "stop_id": assignment["stop_id"],
            "stop_name": assignment["stop_name"],
            "stop_distance_km": assignment["distance_from_start_km"],
            "route_id": assignment["route_id"],
        },
    })


@students_bp.route("/api/students", methods=["GET"])
@login_required("admin")
def list_students():
    rows = run_query(
        """SELECT s.id, s.name, s.register_no, s.phone, u.username,
                  sba.bus_id, b.bus_name, sba.stop_id, bs.stop_name
           FROM students s
           JOIN users u ON u.id = s.user_id
           LEFT JOIN student_bus_assignments sba ON sba.student_id = s.id
           LEFT JOIN buses b ON b.id = sba.bus_id
           LEFT JOIN bus_stops bs ON bs.id = sba.stop_id
           ORDER BY s.id""",
        fetch=True,
    )
    return jsonify({"success": True, "students": rows})
