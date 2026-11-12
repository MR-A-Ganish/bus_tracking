"""
Smart College Bus Tracking and Transportation Management System
Flask backend entry point.

Run with:  python app.py
(see README.md in the project root for full setup instructions)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))  # allow `import config`, `import database`, etc.

from flask import Flask, send_from_directory
from flask import request, jsonify, g
import psycopg
from psycopg_pool import PoolTimeout, TooManyRequests
from werkzeug.exceptions import HTTPException
from datetime import timedelta

from config import SECRET_KEY
from routes.auth import auth_bp
from routes.students import students_bp
from routes.buses import buses_bp
from routes.eta import eta_bp
from routes.attendance import attendance_bp
from routes.notifications import notifications_bp
from routes.admin import admin_bp
from routes.drivers import drivers_bp
from routes.driver import driver_bp
from routes.maps import maps_bp
from routes.route_management import route_management_bp
from services.bus_simulation import start_background_simulation

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
app.secret_key = SECRET_KEY
if os.environ.get("TRUST_PROXY", "false").lower() == "true":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("APP_ENV") == "production",
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=262144)
from routes.tracking import tracking_bp
app.register_blueprint(tracking_bp)

@app.before_request
def validate_api_write():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            return jsonify(success=False, message="Cross-origin writes are not allowed"), 403
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify(success=False, message="Cross-site writes are not allowed"), 403
        if request.is_json:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify(success=False, message="A JSON object is required"), 400
            for field in ("bus_id", "stop_id", "route_id", "capacity"):
                value = data.get(field)
                if value is not None:
                    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                        return jsonify(success=False,message=f"Invalid {field}"),400
                    if field == "capacity" and value > 200:
                        return jsonify(success=False,message="Capacity must be between 1 and 200"),400
            limits = {"username": 50, "password": 256, "name": 100, "bus_name": 50,
                      "driver_name": 100, "phone": 20, "license_no": 50, "register_no": 50}
            for field, limit in limits.items():
                value = data.get(field)
                if value is not None and (not isinstance(value, str) or len(value) > limit):
                    return jsonify(success=False, message=f"Invalid {field}"), 400
            if request.path.startswith("/api/admin/") and data.get("password") and len(data["password"]) < 12:
                return jsonify(success=False,message="New passwords must contain at least 12 characters"),400



@app.after_request
def finish_transaction(response):
    connection = g.get("db_connection")
    if connection:
        try:
            if response.status_code < 400:
                connection.commit()
            else:
                connection.rollback()
        except psycopg.IntegrityError:
            connection.rollback()
            response = jsonify(success=False, message="This change conflicts with existing records or assignments")
            response.status_code = 409
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), camera=(self), microphone=()"
    return response


@app.teardown_request
def close_transaction(error):
    context = g.pop("db_context", None)
    g.pop("db_connection", None)
    if context:
        context.__exit__(type(error) if error else None,error,error.__traceback__ if error else None)


@app.errorhandler(psycopg.IntegrityError)
def invalid_relationship(error):
    return jsonify(success=False, message="This change conflicts with existing records or assignments"), 409


@app.errorhandler(psycopg.DataError)
def invalid_database_value(error):
    return jsonify(success=False, message="One or more values are invalid"), 400


@app.errorhandler(PoolTimeout)
@app.errorhandler(TooManyRequests)
@app.errorhandler(psycopg.OperationalError)
def database_unavailable(error):
    app.logger.error("Database connection unavailable")
    return jsonify(success=False, message="Database temporarily unavailable. Please retry."), 503


@app.errorhandler(HTTPException)
def api_http_error(error):
    if request.path.startswith("/api/"):
        return jsonify(success=False, message=error.description), error.code
    return error


@app.get("/api/health")
def health():
    from database import run_query
    try:
        migration = run_query("SELECT name FROM schema_migrations WHERE name='003_vadalur_route.sql'", fetch_one=True)
        if not migration:
            return jsonify(success=False,message="Database migration pending"),503
        return jsonify(success=True,revision=os.environ.get("RENDER_GIT_COMMIT", "local"),tracking="gps")
    except Exception as error:
        app.logger.exception("Database health check failed (%s)",type(error).__name__)
        return jsonify(success=False, message="Database unavailable",revision=os.environ.get("RENDER_GIT_COMMIT","local")),503


app.register_blueprint(auth_bp)
app.register_blueprint(students_bp)
app.register_blueprint(buses_bp)
app.register_blueprint(eta_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(drivers_bp)
app.register_blueprint(driver_bp)
app.register_blueprint(maps_bp)
app.register_blueprint(route_management_bp)

# Render runs Flask through Gunicorn, which imports this module rather than
# executing it as __main__. Start the simulation here so it also runs there.
start_background_simulation()


# ---------------------------------------------------------------
# Serve the frontend (plain HTML/CSS/JS) directly from Flask so the
# whole project can be run with a single `python app.py` command.
# ---------------------------------------------------------------
@app.get("/favicon.ico")
def favicon():
    return "",204


@app.route("/")
def serve_login():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    print("=" * 60)
    print("Smart College Bus System backend running at http://127.0.0.1:5000")
    print("Open http://127.0.0.1:5000 in your browser to use the app.")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
