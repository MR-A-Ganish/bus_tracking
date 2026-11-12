"""Admin editing of complete ordered routes while preserving referenced stop IDs."""
import math
from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest
from database import run_query
from routes.decorators import login_required

route_management_bp = Blueprint("route_management",__name__)


def validate_stops(stops):
    if not isinstance(stops,list) or not 2 <= len(stops) <= 100:
        raise BadRequest("A route needs between 2 and 100 stops")
    identifiers = set()
    previous_distance = -1
    for index,stop in enumerate(stops):
        if not isinstance(stop,dict):
            raise BadRequest("Each stop must contain a name, coordinates and distance")
        name = stop.get("stop_name")
        if not isinstance(name,str) or not name.strip() or len(name)>100:
            raise BadRequest("Each stop needs a name of at most 100 characters")
        identifier = stop.get("id")
        if identifier is not None:
            if type(identifier) is not int or identifier < 1 or identifier in identifiers:
                raise BadRequest("Stop IDs must be distinct positive integers")
            identifiers.add(identifier)
        for field,minimum,maximum in [("latitude",-90,90),("longitude",-180,180),("distance_from_start_km",0,2000)]:
            value = stop.get(field)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum <= value <= maximum:
                raise BadRequest(f"Invalid {field} for stop {index+1}")
        distance = stop["distance_from_start_km"]
        if distance < previous_distance or (index==0 and distance != 0):
            raise BadRequest("Start at 0 km and keep cumulative distances in travel order")
        previous_distance = distance
    return stops


@route_management_bp.put("/api/admin/routes/<int:route_id>/stops")
@login_required("admin")
def save_route_stops(route_id):
    data = request.get_json(silent=True) or {}
    stops = validate_stops(data.get("stops"))
    # Trip start and GPS ingestion lock the bus first as well.
    buses = run_query("SELECT id FROM buses WHERE route_id=%s ORDER BY id FOR UPDATE",(route_id,),fetch=True)
    route = run_query("SELECT id FROM routes WHERE id=%s FOR UPDATE",(route_id,),fetch_one=True)
    if not route:
        return jsonify(success=False,message="Route not found"),404
    active = run_query("SELECT t.id FROM bus_trips t JOIN buses b ON b.id=t.bus_id WHERE b.route_id=%s AND t.ended_at IS NULL LIMIT 1",(route_id,),fetch_one=True)
    if active:
        return jsonify(success=False,message="End active trips on this route before changing its stop order"),409
    existing = run_query("SELECT id FROM bus_stops WHERE route_id=%s",(route_id,),fetch=True)
    existing_ids = {stop["id"] for stop in existing}
    submitted_ids = {stop["id"] for stop in stops if stop.get("id") is not None}
    if not submitted_ids.issubset(existing_ids):
        raise BadRequest("A stop does not belong to the selected route")
    removed = list(existing_ids-submitted_ids)
    if removed:
        referenced = run_query("""SELECT 1 FROM student_bus_assignments WHERE stop_id=ANY(%s)
                                  UNION ALL SELECT 1 FROM attendance WHERE stop_id=ANY(%s) LIMIT 1""",(removed,removed),fetch_one=True)
        if referenced:
            return jsonify(success=False,message="A removed stop has student assignments or attendance history. Keep it, or reassign students if no history exists."),409
    saved = []
    for index,stop in enumerate(stops):
        values = (stop["stop_name"].strip(),index,stop["distance_from_start_km"],stop["latitude"],stop["longitude"])
        if stop.get("id") is None:
            identifier = run_query("INSERT INTO bus_stops(stop_name,sequence_order,distance_from_start_km,latitude,longitude,route_id) VALUES (%s,%s,%s,%s,%s,%s)",values+(route_id,),commit=True)
        else:
            identifier = stop["id"]
            run_query("UPDATE bus_stops SET stop_name=%s,sequence_order=%s,distance_from_start_km=%s,latitude=%s,longitude=%s WHERE id=%s",values+(identifier,),commit=True)
        saved.append(identifier)
    for bus in buses:
        run_query("""UPDATE bus_locations SET current_stop_id=%s,next_stop_id=%s,approach_notified_stop_id=NULL,
                     status='not_started',distance_covered_km=0,sharing_active=FALSE,college_entry_detected=FALSE,
                     college_entry_time=NULL WHERE bus_id=%s""",(saved[0],saved[1],bus["id"]),commit=True)
    if removed:
        run_query("DELETE FROM bus_stops WHERE id=ANY(%s)",(removed,),commit=True)
    run_query("UPDATE routes SET start_point=%s,end_point=%s WHERE id=%s",(stops[0]["stop_name"].strip(),stops[-1]["stop_name"].strip(),route_id),commit=True)
    return jsonify(success=True,message="Route stops saved")
