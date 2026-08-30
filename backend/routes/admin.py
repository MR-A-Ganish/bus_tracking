from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash
from database import run_query
from routes.decorators import login_required
from services.route_optimizer import optimize_route

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/api/college-entry", methods=["GET"])
@login_required("admin")
def college_entry_status():
    bus_id = request.args.get("bus_id", type=int)
    query = """SELECT b.id AS bus_id, b.bus_name, bl.college_entry_detected, bl.college_entry_time, bl.status
               FROM buses b JOIN bus_locations bl ON bl.bus_id = b.id"""
    params = ()
    if bus_id:
        query += " WHERE b.id=%s"
        params = (bus_id,)
    rows = run_query(query, params, fetch=True)

    for r in rows:
        if r["college_entry_detected"]:
            time_str = r["college_entry_time"].strftime("%I:%M %p") if r["college_entry_time"] else ""
            r["message"] = f"{r['bus_name']} has entered IFET College at {time_str}."
        else:
            r["message"] = f"{r['bus_name']} has not entered the college yet."

    return jsonify({"success": True, "college_entry_status": rows})


@admin_bp.route("/api/route-optimize", methods=["GET"])
@login_required("admin")
def route_optimize():
    bus_id = request.args.get("bus_id", type=int)
    traffic_map = None
    if bus_id:
        loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
        if loc:
            # apply the bus's current traffic reading to every remaining segment as a simple demo
            from services.route_optimizer import ROAD_SEGMENTS
            traffic_map = {seg: loc["traffic_condition"] for seg in ROAD_SEGMENTS.keys()}
    result = optimize_route(traffic_map)
    return jsonify({"success": True, **result})


# ------------------------------------------------------------------
# Management: lookup data for the admin panel's add/edit forms
# ------------------------------------------------------------------
@admin_bp.route("/api/admin/lookup", methods=["GET"])
@login_required("admin")
def admin_lookup():
    buses = run_query("SELECT id, bus_name, route_id FROM buses ORDER BY bus_name", fetch=True)
    routes = run_query("SELECT id, route_name FROM routes ORDER BY route_name", fetch=True)
    stops = run_query(
        """SELECT id, route_id, stop_name, sequence_order, distance_from_start_km, latitude, longitude
           FROM bus_stops ORDER BY route_id, sequence_order""",
        fetch=True,
    )
    return jsonify({"success": True, "buses": buses, "routes": routes, "stops": stops})


# ------------------------------------------------------------------
# Management: students
# ------------------------------------------------------------------
@admin_bp.route("/api/admin/students", methods=["POST"])
@login_required("admin")
def create_student():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    register_no = (data.get("register_no") or "").strip() or None
    phone = (data.get("phone") or "").strip() or None
    bus_id = data.get("bus_id")
    stop_id = data.get("stop_id")

    if not username or not password or not name:
        return jsonify({"success": False, "message": "Username, password and name are required"}), 400

    if run_query("SELECT id FROM users WHERE username=%s", (username,), fetch_one=True):
        return jsonify({"success": False, "message": "That username is already taken"}), 409

    user_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'student')",
        (username, generate_password_hash(password)), commit=True,
    )
    student_id = run_query(
        "INSERT INTO students (user_id, name, register_no, phone) VALUES (%s,%s,%s,%s)",
        (user_id, name, register_no, phone), commit=True,
    )

    if bus_id and stop_id:
        run_query(
            "INSERT INTO student_bus_assignments (student_id, bus_id, stop_id) VALUES (%s,%s,%s)",
            (student_id, bus_id, stop_id), commit=True,
        )

    return jsonify({"success": True, "student_id": student_id})


@admin_bp.route("/api/admin/students/<int:student_id>", methods=["PUT"])
@login_required("admin")
def update_student(student_id):
    data = request.get_json(force=True) or {}
    student = run_query("SELECT * FROM students WHERE id=%s", (student_id,), fetch_one=True)
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    run_query(
        """UPDATE students SET name=COALESCE(%s,name), register_no=COALESCE(%s,register_no),
           phone=COALESCE(%s,phone) WHERE id=%s""",
        (data.get("name") or None, data.get("register_no") or None, data.get("phone") or None, student_id),
        commit=True,
    )

    new_password = data.get("password") or None
    if new_password:
        run_query(
            "UPDATE users SET password=%s WHERE id=%s",
            (generate_password_hash(new_password), student["user_id"]), commit=True,
        )

    bus_id = data.get("bus_id")
    stop_id = data.get("stop_id")
    if bus_id and stop_id:
        existing = run_query(
            "SELECT id FROM student_bus_assignments WHERE student_id=%s", (student_id,), fetch_one=True
        )
        if existing:
            run_query(
                "UPDATE student_bus_assignments SET bus_id=%s, stop_id=%s WHERE student_id=%s",
                (bus_id, stop_id, student_id), commit=True,
            )
        else:
            run_query(
                "INSERT INTO student_bus_assignments (student_id, bus_id, stop_id) VALUES (%s,%s,%s)",
                (student_id, bus_id, stop_id), commit=True,
            )

    return jsonify({"success": True})


@admin_bp.route("/api/admin/students/<int:student_id>", methods=["DELETE"])
@login_required("admin")
def delete_student(student_id):
    student = run_query("SELECT * FROM students WHERE id=%s", (student_id,), fetch_one=True)
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    run_query("DELETE FROM attendance WHERE student_id=%s", (student_id,), commit=True)
    run_query("DELETE FROM notifications WHERE student_id=%s", (student_id,), commit=True)
    run_query("DELETE FROM student_bus_assignments WHERE student_id=%s", (student_id,), commit=True)
    run_query("DELETE FROM students WHERE id=%s", (student_id,), commit=True)
    run_query("DELETE FROM users WHERE id=%s", (student["user_id"],), commit=True)
    return jsonify({"success": True})


# ------------------------------------------------------------------
# Management: buses
# ------------------------------------------------------------------
@admin_bp.route("/api/admin/buses", methods=["POST"])
@login_required("admin")
def create_bus():
    data = request.get_json(force=True) or {}
    bus_name = (data.get("bus_name") or "").strip()
    driver_name = (data.get("driver_name") or "").strip() or None
    capacity = data.get("capacity") or 50
    route_id = data.get("route_id")

    if not bus_name or not route_id:
        return jsonify({"success": False, "message": "Bus name and route are required"}), 400

    stops = run_query(
        "SELECT id FROM bus_stops WHERE route_id=%s ORDER BY sequence_order ASC LIMIT 2",
        (route_id,), fetch=True,
    )
    if not stops:
        return jsonify({"success": False, "message": "Selected route has no stops configured"}), 400

    bus_id = run_query(
        "INSERT INTO buses (bus_name, driver_name, capacity, current_passengers, route_id) VALUES (%s,%s,%s,0,%s)",
        (bus_name, driver_name, capacity, route_id), commit=True,
    )
    run_query(
        """INSERT INTO bus_locations (bus_id, distance_covered_km, current_stop_id, next_stop_id, status, traffic_condition, speed_kmph)
           VALUES (%s,0,%s,%s,'not_started','low',30)""",
        (bus_id, stops[0]["id"], stops[1]["id"] if len(stops) > 1 else None), commit=True,
    )
    return jsonify({"success": True, "bus_id": bus_id})


@admin_bp.route("/api/admin/buses/<int:bus_id>", methods=["PUT"])
@login_required("admin")
def update_bus(bus_id):
    data = request.get_json(force=True) or {}
    if not run_query("SELECT id FROM buses WHERE id=%s", (bus_id,), fetch_one=True):
        return jsonify({"success": False, "message": "Bus not found"}), 404

    run_query(
        """UPDATE buses SET bus_name=COALESCE(%s,bus_name), driver_name=COALESCE(%s,driver_name),
           capacity=COALESCE(%s,capacity) WHERE id=%s""",
        (data.get("bus_name") or None, data.get("driver_name") or None, data.get("capacity") or None, bus_id),
        commit=True,
    )
    return jsonify({"success": True})


@admin_bp.route("/api/admin/buses/<int:bus_id>", methods=["DELETE"])
@login_required("admin")
def delete_bus(bus_id):
    if not run_query("SELECT id FROM buses WHERE id=%s", (bus_id,), fetch_one=True):
        return jsonify({"success": False, "message": "Bus not found"}), 404

    run_query("DELETE FROM attendance WHERE bus_id=%s", (bus_id,), commit=True)
    run_query("DELETE FROM eta_predictions WHERE bus_id=%s", (bus_id,), commit=True)
    run_query("DELETE FROM notifications WHERE bus_id=%s", (bus_id,), commit=True)
    run_query("DELETE FROM student_bus_assignments WHERE bus_id=%s", (bus_id,), commit=True)
    run_query("DELETE FROM bus_locations WHERE bus_id=%s", (bus_id,), commit=True)
    run_query("DELETE FROM buses WHERE id=%s", (bus_id,), commit=True)
    return jsonify({"success": True})


# ------------------------------------------------------------------
# Management: admin accounts
# ------------------------------------------------------------------
@admin_bp.route("/api/admin/admins", methods=["GET"])
@login_required("admin")
def list_admins():
    rows = run_query(
        "SELECT a.id, a.name, u.username FROM admins a JOIN users u ON u.id = a.user_id ORDER BY a.id",
        fetch=True,
    )
    return jsonify({"success": True, "admins": rows})


@admin_bp.route("/api/admin/admins", methods=["POST"])
@login_required("admin")
def create_admin():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    if not username or not password or not name:
        return jsonify({"success": False, "message": "Username, password and name are required"}), 400

    if run_query("SELECT id FROM users WHERE username=%s", (username,), fetch_one=True):
        return jsonify({"success": False, "message": "That username is already taken"}), 409

    user_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'admin')",
        (username, generate_password_hash(password)), commit=True,
    )
    admin_id = run_query("INSERT INTO admins (user_id, name) VALUES (%s,%s)", (user_id, name), commit=True)
    return jsonify({"success": True, "admin_id": admin_id})


@admin_bp.route("/api/admin/admins/<int:admin_id>", methods=["DELETE"])
@login_required("admin")
def delete_admin(admin_id):
    admin_row = run_query("SELECT * FROM admins WHERE id=%s", (admin_id,), fetch_one=True)
    if not admin_row:
        return jsonify({"success": False, "message": "Admin not found"}), 404
    if session.get("admin_id") == admin_id:
        return jsonify({"success": False, "message": "You cannot delete the account you're logged in with"}), 400

    run_query("DELETE FROM admins WHERE id=%s", (admin_id,), commit=True)
    run_query("DELETE FROM users WHERE id=%s", (admin_row["user_id"],), commit=True)
    return jsonify({"success": True})


# ------------------------------------------------------------------
# Management: driver accounts
# ------------------------------------------------------------------
@admin_bp.route("/api/admin/drivers", methods=["GET"])
@login_required("admin")
def list_drivers():
    rows = run_query(
        """SELECT d.id, d.name, d.phone, d.license_no, u.username, d.bus_id, b.bus_name
           FROM drivers d
           JOIN users u ON u.id = d.user_id
           LEFT JOIN buses b ON b.id = d.bus_id
           ORDER BY d.id""",
        fetch=True,
    )
    return jsonify({"success": True, "drivers": rows})


@admin_bp.route("/api/admin/drivers", methods=["POST"])
@login_required("admin")
def create_driver():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip() or None
    license_no = (data.get("license_no") or "").strip() or None
    bus_id = data.get("bus_id") or None

    if not username or not password or not name:
        return jsonify({"success": False, "message": "Username, password and name are required"}), 400

    if run_query("SELECT id FROM users WHERE username=%s", (username,), fetch_one=True):
        return jsonify({"success": False, "message": "That username is already taken"}), 409

    user_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'driver')",
        (username, generate_password_hash(password)), commit=True,
    )
    driver_id = run_query(
        "INSERT INTO drivers (user_id, name, phone, license_no, bus_id) VALUES (%s,%s,%s,%s,%s)",
        (user_id, name, phone, license_no, bus_id), commit=True,
    )
    return jsonify({"success": True, "driver_id": driver_id})


@admin_bp.route("/api/admin/drivers/<int:driver_id>", methods=["PUT"])
@login_required("admin")
def update_driver(driver_id):
    data = request.get_json(force=True) or {}
    driver = run_query("SELECT * FROM drivers WHERE id=%s", (driver_id,), fetch_one=True)
    if not driver:
        return jsonify({"success": False, "message": "Driver not found"}), 404

    run_query(
        """UPDATE drivers SET name=COALESCE(%s,name), phone=COALESCE(%s,phone),
           license_no=COALESCE(%s,license_no), bus_id=%s WHERE id=%s""",
        (data.get("name") or None, data.get("phone") or None, data.get("license_no") or None,
         data.get("bus_id") or None, driver_id),
        commit=True,
    )

    new_password = data.get("password") or None
    if new_password:
        run_query(
            "UPDATE users SET password=%s WHERE id=%s",
            (generate_password_hash(new_password), driver["user_id"]), commit=True,
        )

    return jsonify({"success": True})


@admin_bp.route("/api/admin/drivers/<int:driver_id>", methods=["DELETE"])
@login_required("admin")
def delete_driver(driver_id):
    driver = run_query("SELECT * FROM drivers WHERE id=%s", (driver_id,), fetch_one=True)
    if not driver:
        return jsonify({"success": False, "message": "Driver not found"}), 404

    run_query("DELETE FROM drivers WHERE id=%s", (driver_id,), commit=True)
    run_query("DELETE FROM users WHERE id=%s", (driver["user_id"],), commit=True)
    return jsonify({"success": True})
