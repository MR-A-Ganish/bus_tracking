from flask import Blueprint, request, jsonify
from database import run_query
from routes.decorators import login_required

eta_bp = Blueprint("eta", __name__)


@eta_bp.route("/api/eta/predict", methods=["GET"])
@login_required()
def eta_predict():
    """
    Query params: bus_id, stop_id (the TARGET stop - e.g. the student's
    assigned stop, NOT necessarily the college).
    """
    bus_id = request.args.get("bus_id", type=int)
    stop_id = request.args.get("stop_id", type=int)
    if not bus_id or not stop_id:
        return jsonify({"success": False, "message": "bus_id and stop_id are required"}), 400

    from routes.buses import can_access_bus
    if not can_access_bus(bus_id):
        return jsonify(success=False, message="Bus is not assigned to you"), 403
    loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
    target_stop = run_query("SELECT s.* FROM bus_stops s JOIN buses b ON b.route_id=s.route_id WHERE s.id=%s AND b.id=%s", (stop_id,bus_id), fetch_one=True)
    if not loc or not target_stop:
        return jsonify({"success": False, "message": "Bus or stop not found"}), 404

    if loc.get("location_source") == "gps":
        from routes.buses import annotate_location
        from math import radians, sin, cos, atan2, sqrt
        annotate_location(loc)
        if loc["is_stale"] or target_stop["latitude"] is None or target_stop["longitude"] is None:
            return jsonify(success=False, message="ETA unavailable: GPS offline or stop coordinates missing")
        lat1, lat2 = radians(loc["latitude"]), radians(float(target_stop["latitude"]))
        dlat = lat2-lat1
        dlng = radians(float(target_stop["longitude"]) - loc["longitude"])
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlng/2)**2
        distance = 6371 * 2 * atan2(sqrt(a), sqrt(max(0, 1-a)))
        return jsonify(success=True, eta_minutes=round(distance / max(loc["speed_kmph"], 15) * 60, 1),
                       distance_km=round(distance, 2), stops_remaining=None,
                       is_prototype=True, model="straight-line estimate", estimate_label="Approximate ETA (straight-line distance)")

    from config import SIMULATION_ENABLED
    if not SIMULATION_ENABLED:
        return jsonify(success=False,message="ETA unavailable until the driver shares GPS")
    distance_km = target_stop["distance_from_start_km"] - loc["distance_covered_km"]

    if distance_km <= 0:
        return jsonify({
            "success": True,
            "eta_minutes": 0,
            "distance_km": 0,
            "stops_remaining": 0,
            "message": "Bus has already reached or passed this stop",
        })

    all_stops = run_query(
        "SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order ASC",
        (target_stop["route_id"],), fetch=True,
    )
    stops_between = [
        s for s in all_stops
        if loc["distance_covered_km"] < s["distance_from_start_km"] < target_stop["distance_from_start_km"]
    ]

    from ai.eta_model import predict_eta
    result = predict_eta(
        distance_km=distance_km,
        avg_speed_kmph=loc["speed_kmph"],
        traffic_condition=loc["traffic_condition"],
        stops_remaining=len(stops_between),
    )

    run_query(
        """INSERT INTO eta_predictions (bus_id, stop_id, predicted_eta_minutes, distance_km, traffic_condition)
           VALUES (%s,%s,%s,%s,%s)""",
        (bus_id, stop_id, result["eta_minutes"], round(distance_km, 2), loc["traffic_condition"]),
        commit=True,
    )

    return jsonify({
        "success": True,
        "eta_minutes": result["eta_minutes"],
        "distance_km": round(distance_km, 2),
        "traffic_condition": loc["traffic_condition"],
        "stops_remaining": len(stops_between),
        "is_prototype": result["is_prototype"],
        "model": result["model"],
    })
