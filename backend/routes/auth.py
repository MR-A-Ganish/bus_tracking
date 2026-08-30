from flask import Blueprint, request, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash
from database import run_query

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = run_query("SELECT * FROM users WHERE username=%s", (username,), fetch_one=True)
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"success": False, "message": "Invalid username or password"}), 401

    session["user_id"] = user["id"]
    session["role"] = user["role"]

    profile = {"id": user["id"], "username": user["username"], "role": user["role"]}

    if user["role"] == "student":
        student = run_query("SELECT * FROM students WHERE user_id=%s", (user["id"],), fetch_one=True)
        session["student_id"] = student["id"]
        profile["student_id"] = student["id"]
        profile["name"] = student["name"]
    elif user["role"] == "driver":
        driver = run_query("SELECT * FROM drivers WHERE user_id=%s", (user["id"],), fetch_one=True)
        session["driver_id"] = driver["id"]
        profile["driver_id"] = driver["id"]
        profile["name"] = driver["name"]
    else:
        admin = run_query("SELECT * FROM admins WHERE user_id=%s", (user["id"],), fetch_one=True)
        session["admin_id"] = admin["id"]
        profile["admin_id"] = admin["id"]
        profile["name"] = admin["name"]

    return jsonify({"success": True, "user": profile})


@auth_bp.route("/api/register/lookup", methods=["GET"])
def register_lookup():
    """Public (no login) bus/stop list so the signup form can offer a bus+stop picker."""
    buses = run_query("SELECT id, bus_name, route_id FROM buses ORDER BY bus_name", fetch=True)
    stops = run_query(
        "SELECT id, route_id, stop_name, sequence_order FROM bus_stops ORDER BY route_id, sequence_order",
        fetch=True,
    )
    return jsonify({"success": True, "buses": buses, "stops": stops})


@auth_bp.route("/api/register", methods=["POST"])
def register():
    """Student self-signup. Admin accounts are never created through this endpoint -
    they're managed exclusively from the Management dashboard's Admins tab."""
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
    if len(password) < 4:
        return jsonify({"success": False, "message": "Password must be at least 4 characters"}), 400

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

    session["user_id"] = user_id
    session["role"] = "student"
    session["student_id"] = student_id

    return jsonify({
        "success": True,
        "user": {"id": user_id, "username": username, "role": "student", "student_id": student_id, "name": name},
    })


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@auth_bp.route("/api/session", methods=["GET"])
def get_session():
    if "user_id" not in session:
        return jsonify({"logged_in": False}), 200
    return jsonify({
        "logged_in": True,
        "role": session.get("role"),
        "student_id": session.get("student_id"),
        "admin_id": session.get("admin_id"),
        "driver_id": session.get("driver_id"),
    })
