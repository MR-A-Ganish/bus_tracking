"""
Run this ONCE after creating the database with database/schema.sql:

    python seed.py

It creates the demo login accounts (with securely hashed passwords) and
sample student -> bus -> stop assignments described in the project README.
Safe to re-run (it clears and re-creates the demo rows each time).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from werkzeug.security import generate_password_hash
from database import run_query


def seed():
    if run_query("SELECT COUNT(*) AS count FROM users", fetch_one=True)["count"]:
        raise RuntimeError("Demo seeding requires an empty users table. Existing accounts must be preserved.")
    print("Seeding demo users...")

    # Clear old demo data (children first, to satisfy foreign keys)
    run_query("DELETE FROM attendance", commit=True)
    run_query("DELETE FROM student_bus_assignments", commit=True)
    run_query("DELETE FROM students", commit=True)
    run_query("DELETE FROM admins", commit=True)
    run_query("DELETE FROM drivers", commit=True)
    run_query("DELETE FROM users", commit=True)

    # --- Users ---
    student01_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'student') RETURNING id",
        ("student01", generate_password_hash("1234")), fetch_one=True, commit=True,
    )
    student01_id = student01_id["id"]
    student02_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'student') RETURNING id",
        ("student02", generate_password_hash("1234")), fetch_one=True, commit=True,
    )
    student02_id = student02_id["id"]
    admin01_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'admin') RETURNING id",
        ("admin01", generate_password_hash("admin123")), fetch_one=True, commit=True,
    )
    admin01_id = admin01_id["id"]
    driver01_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'driver') RETURNING id",
        ("driver01", generate_password_hash("driver123")), fetch_one=True, commit=True,
    )
    driver01_id = driver01_id["id"]

    # --- Students ---
    priya_id = run_query(
        "INSERT INTO students (user_id, name, register_no, phone) VALUES (%s,%s,%s,%s) RETURNING id",
        (student01_id, "Priya R", "22ECE045", "9876543210"), fetch_one=True, commit=True,
    )
    priya_id = priya_id["id"]
    arun_id = run_query(
        "INSERT INTO students (user_id, name, register_no, phone) VALUES (%s,%s,%s,%s) RETURNING id",
        (student02_id, "Arun K", "22ECE012", "9876543211"), fetch_one=True, commit=True,
    )
    arun_id = arun_id["id"]

    # --- Admin ---
    run_query(
        "INSERT INTO admins (user_id, name) VALUES (%s,%s)",
        (admin01_id, "Transport Officer"), commit=True,
    )

    # --- Driver ---
    run_query(
        "INSERT INTO drivers (user_id, name, bus_id) VALUES (%s,%s,%s)",
        (driver01_id, "Mr. Raja", 1), commit=True,
    )

    # --- Bus stop lookups ---
    kandamangalam = run_query("SELECT id FROM bus_stops WHERE stop_name='Kandamangalam'", fetch_one=True)
    thirunavalur = run_query("SELECT id FROM bus_stops WHERE stop_name='Thirunavalur'", fetch_one=True)

    # --- Assignments ---
    run_query(
        "INSERT INTO student_bus_assignments (student_id, bus_id, stop_id) VALUES (%s,1,%s)",
        (priya_id, kandamangalam["id"]), commit=True,
    )
    run_query(
        "INSERT INTO student_bus_assignments (student_id, bus_id, stop_id) VALUES (%s,1,%s)",
        (arun_id, thirunavalur["id"]), commit=True,
    )

    # Reset bus passenger counts / live location state for a clean demo run
    run_query("UPDATE buses SET current_passengers=0", commit=True)
    run_query(
        """UPDATE bus_locations SET distance_covered_km=0, status='not_started',
           current_stop_id=(SELECT id FROM bus_stops WHERE stop_name='Villupuram Bus Stand'),
           next_stop_id=(SELECT id FROM bus_stops WHERE stop_name='Mundiyampakkam'),
           college_entry_detected=FALSE, college_entry_time=NULL""",
        commit=True,
    )

    print("Done. Demo accounts:")
    print("  Student login: student01 / 1234   (Priya R, Bus 01, stop: Kandamangalam)")
    print("  Student login: student02 / 1234   (Arun K, Bus 01, stop: Thirunavalur)")
    print("  Driver login:  driver01 / driver123 (Mr. Raja, Bus 01)")
    print("  Admin login:   admin01 / admin123")


if __name__ == "__main__":
    seed()
