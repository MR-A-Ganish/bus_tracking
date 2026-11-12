"""Create operational accounts or change passwords using a hidden prompt."""
import argparse
from getpass import getpass
from werkzeug.security import generate_password_hash
from database import get_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("--role", choices=["admin", "driver", "student"])
    parser.add_argument("--name")
    parser.add_argument("--bus-id", type=int)
    parser.add_argument("--stop-id", type=int)
    parser.add_argument("--reset-password", action="store_true")
    args = parser.parse_args()
    password = getpass("New password (at least 12 characters): ")
    if len(password) < 12 or password != getpass("Repeat password: "):
        parser.error("Passwords must match and contain at least 12 characters")
    with get_connection() as conn:
        if args.reset_password:
            result = conn.execute("UPDATE users SET password=%s WHERE username=%s", (generate_password_hash(password), args.username))
            if result.rowcount != 1:
                parser.error("Account not found")
        else:
            if not args.role or not args.name:
                parser.error("New accounts require --role and --name")
            if args.role in ("student", "driver") and not args.bus_id:
                parser.error("Drivers and students require --bus-id")
            if args.role == "student":
                stop = conn.execute("""SELECT s.id FROM bus_stops s JOIN buses b ON b.route_id=s.route_id
                                    WHERE s.id=%s AND b.id=%s""", (args.stop_id, args.bus_id)).fetchone()
                if not stop:
                    parser.error("--stop-id must belong to the bus route")
            user = conn.execute("INSERT INTO users(username,password,role) VALUES (%s,%s,%s) RETURNING id",
                                (args.username, generate_password_hash(password), args.role)).fetchone()
            if args.role == "admin":
                conn.execute("INSERT INTO admins(user_id,name) VALUES (%s,%s)", (user["id"], args.name))
            elif args.role == "driver":
                conn.execute("INSERT INTO drivers(user_id,name,bus_id) VALUES (%s,%s,%s)", (user["id"], args.name, args.bus_id))
            else:
                student = conn.execute("INSERT INTO students(user_id,name) VALUES (%s,%s) RETURNING id", (user["id"], args.name)).fetchone()
                conn.execute("INSERT INTO student_bus_assignments(student_id,bus_id,stop_id) VALUES (%s,%s,%s)", (student["id"], args.bus_id, args.stop_id))
    print("Account updated successfully")


if __name__ == "__main__":
    main()
