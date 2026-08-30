from flask import Blueprint, request, jsonify
from database import run_query
from routes.decorators import login_required
from ai.eta_model import predict_eta
from services.geofence import haversine_km, is_gps_live

eta_bp = Blueprint("eta", __name__)


@eta_bp.route("/api/eta/predict", methods=["GET"])
@login_required()
def eta_predict():
    """
    Query params: bus_id, stop_id (the TARGET stop - e.g. the student's
    assigned stop, NOT necessarily the college).

    When a driver is actively streaming real GPS for this bus, distance is
    computed with a real haversine calculation from the live position to
    the target stop; otherwise it falls back to the simulated
    distance_covered_km bookkeeping.
    """
    bus_id = request.args.get("bus_id", type=int)
    stop_id = request.args.get("stop_id", type=int)
    if not bus_id or not stop_id:
        return jsonify({"success": False, "message": "bus_id and stop_id are required"}), 400

    loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
    target_stop = run_query("SELECT * FROM bus_stops WHERE id=%s", (stop_id,), fetch_one=True)
    if not loc or not target_stop:
        return jsonify({"success": False, "message": "Bus or stop not found"}), 404

    all_stops = run_query(
        "SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order ASC",
        (target_stop["route_id"],), fetch=True,
    )

    live = is_gps_live(loc["gps_updated_at"]) and loc["gps_lat"] is not None

    if live:
        current_stop = next((s for s in all_stops if s["id"] == loc["current_stop_id"]), None)
        current_seq = current_stop["sequence_order"] if current_stop else -1
        if current_seq >= target_stop["sequence_order"]:
            return jsonify({
                "success": True, "eta_minutes": 0, "distance_km": 0, "is_live": True,
                "message": "Bus has already reached or passed this stop",
            })
        distance_km = haversine_km(loc["gps_lat"], loc["gps_lng"], target_stop["latitude"], target_stop["longitude"])
        stops_between = [s for s in all_stops if current_seq < s["sequence_order"] < target_stop["sequence_order"]]
        avg_speed = loc["gps_speed_kmph"] or loc["speed_kmph"]
    else:
        distance_km = target_stop["distance_from_start_km"] - loc["distance_covered_km"]
        if distance_km <= 0:
            return jsonify({
                "success": True, "eta_minutes": 0, "distance_km": 0, "is_live": False,
                "message": "Bus has already reached or passed this stop",
            })
        stops_between = [
            s for s in all_stops
            if loc["distance_covered_km"] < s["distance_from_start_km"] < target_stop["distance_from_start_km"]
        ]
        avg_speed = loc["speed_kmph"]

    result = predict_eta(
        distance_km=distance_km,
        avg_speed_kmph=avg_speed,
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
        "is_live": live,
    })
