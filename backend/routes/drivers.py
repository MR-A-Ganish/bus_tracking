from flask import Blueprint
from routes.driver import my_driver_profile, start_trip

drivers_bp = Blueprint("drivers", __name__)
drivers_bp.add_url_rule("/api/drivers/me", view_func=my_driver_profile, methods=["GET"])
drivers_bp.add_url_rule("/api/drivers/bus/start", view_func=start_trip, methods=["POST"])
