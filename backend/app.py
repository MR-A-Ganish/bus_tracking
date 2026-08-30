"""
Smart College Bus Tracking and Transportation Management System
Flask backend entry point.

Run with:  python app.py
(see README.md in the project root for full setup instructions)
"""

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(__file__))  # allow `import config`, `import database`, etc.

from flask import Flask, send_from_directory
from flask_cors import CORS

from config import SECRET_KEY
from routes.auth import auth_bp
from routes.students import students_bp
from routes.buses import buses_bp
from routes.eta import eta_bp
from routes.attendance import attendance_bp
from routes.notifications import notifications_bp
from routes.admin import admin_bp
from routes.driver import driver_bp
from services.bus_simulation import start_background_simulation

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
app.secret_key = SECRET_KEY
CORS(app, supports_credentials=True)

app.register_blueprint(auth_bp)
app.register_blueprint(students_bp)
app.register_blueprint(buses_bp)
app.register_blueprint(eta_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(driver_bp)

# Started at import time (not just under `if __name__ == "__main__"`) so it
# also runs under a production WSGI server like gunicorn, which imports this
# module and never executes the block below. Run with a single worker
# (gunicorn --workers 1) - each worker would otherwise start its own copy of
# this thread and double-tick every bus.
start_background_simulation()


# ---------------------------------------------------------------
# Serve the frontend (plain HTML/CSS/JS) directly from Flask so the
# whole project can be run with a single `python app.py` command.
# ---------------------------------------------------------------
@app.route("/")
def serve_login():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(FRONTEND_DIR, path)


def _lan_ip():
    """Best-effort local network IP (used only to print a handy URL - never sent anywhere)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    lan_ip = _lan_ip()
    print("=" * 68)
    print("Smart College Bus System backend running")
    print(f"  On this computer:      http://127.0.0.1:5000")
    print(f"  On your phone / LAN:   http://{lan_ip}:5000")
    print("  For a real cross-network demo (driver + student on different")
    print("  networks), run a Cloudflare tunnel in another terminal:")
    print("    cloudflared tunnel --url http://localhost:5000")
    print("  and use the https://*.trycloudflare.com URL it prints instead -")
    print("  the Geolocation API on the driver's phone requires HTTPS.")
    print("=" * 68)
    # debug=False: this process may be reachable from outside localhost
    # (LAN, or a public tunnel) during a demo - the Werkzeug debugger must
    # stay off whenever that's true.
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
