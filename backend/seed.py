"""
Run this ONCE after creating the database with database/schema.sql:

    python seed.py

It creates the demo login accounts (with securely hashed passwords) and
sample student -> bus -> stop / driver -> bus assignments described in the
project README. Safe to re-run (it clears and re-creates the demo rows each
time, and resets any bus to a clean not-started state - including clearing
any live GPS data from a previous test run).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from werkzeug.security import generate_password_hash
from database import run_query


def seed():
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
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'student')",
        ("student01", generate_password_hash("1234")), commit=True,
    )
    student02_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'student')",
        ("student02", generate_password_hash("1234")), commit=True,
    )
    admin01_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'admin')",
        ("admin01", generate_password_hash("admin123")), commit=True,
    )
    driver01_id = run_query(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'driver')",
        ("driver01", generate_password_hash("drive123")), commit=True,
    )

    # --- Students ---
    priya_id = run_query(
        "INSERT INTO students (user_id, name, register_no, phone) VALUES (%s,%s,%s,%s)",
        (student01_id, "Priya R", "22ECE045", "9876543210"), commit=True,
    )
    arun_id = run_query(
        "INSERT INTO students (user_id, name, register_no, phone) VALUES (%s,%s,%s,%s)",
        (student02_id, "Arun K", "22ECE012", "9876543211"), commit=True,
    )

    # --- Admin ---
    run_query(
        "INSERT INTO admins (user_id, name) VALUES (%s,%s)",
        (admin01_id, "Transport Officer"), commit=True,
    )

    # --- Driver (assigned to Bus 01) ---
    run_query(
        "INSERT INTO drivers (user_id, name, phone, license_no, bus_id) VALUES (%s,%s,%s,%s,%s)",
        (driver01_id, "Mr. Raja", "9876500000", "TN31-2019-0004521", 1), commit=True,
    )

    # --- Bus stop lookups (route's first stop / last stop by sequence_order,
    # so this keeps working however many intermediate stops are configured) ---
    first_stop = run_query(
        "SELECT * FROM bus_stops WHERE route_id=1 ORDER BY sequence_order ASC LIMIT 1", fetch_one=True
    )
    second_stop = run_query(
        "SELECT * FROM bus_stops WHERE route_id=1 ORDER BY sequence_order ASC LIMIT 1 OFFSET 1", fetch_one=True
    )
    last_stop = run_query(
        "SELECT * FROM bus_stops WHERE route_id=1 ORDER BY sequence_order DESC LIMIT 1", fetch_one=True
    )
    boarding_stop = second_stop or last_stop

    # --- Assignments (both demo students board at the same convenient stop) ---
    run_query(
        "INSERT INTO student_bus_assignments (student_id, bus_id, stop_id) VALUES (%s,1,%s)",
        (priya_id, boarding_stop["id"]), commit=True,
    )
    run_query(
        "INSERT INTO student_bus_assignments (student_id, bus_id, stop_id) VALUES (%s,1,%s)",
        (arun_id, last_stop["id"]), commit=True,
    )

    # Reset bus passenger counts / live location state for a clean demo run
    run_query("UPDATE buses SET current_passengers=0", commit=True)
    run_query(
        """UPDATE bus_locations SET distance_covered_km=0, status='not_started',
           current_stop_id=%s, next_stop_id=%s,
           college_entry_detected=0, college_entry_time=NULL,
           gps_lat=NULL, gps_lng=NULL, gps_accuracy_m=NULL, gps_speed_kmph=NULL, gps_updated_at=NULL""",
        (first_stop["id"], (second_stop or last_stop)["id"]), commit=True,
    )

    print("Done. Demo accounts:")
    print(f"  Student login: student01 / 1234     (Priya R, Bus 01, stop: {boarding_stop['stop_name']})")
    print(f"  Student login: student02 / 1234     (Arun K, Bus 01, stop: {last_stop['stop_name']})")
    print("  Admin login:   admin01 / admin123")
    print("  Driver login:  driver01 / drive123   (Mr. Raja, Bus 01 - open driver.html and grant location access)")


if __name__ == "__main__":
    seed()
