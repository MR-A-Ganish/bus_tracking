from flask import Blueprint, jsonify

from config import GOOGLE_MAPS_API_KEY
from routes.decorators import login_required


maps_bp = Blueprint("maps", __name__)


@maps_bp.route("/api/maps/config", methods=["GET"])
@login_required()
def map_config():
    """Return the browser-restricted Google Maps JavaScript key after login."""
    return jsonify({"success": True, "google_maps_api_key": GOOGLE_MAPS_API_KEY})
