"""Stop events derived from accepted GPS fixes in the same database transaction."""
from math import radians, sin, cos, atan2, sqrt

GEOFENCE_RADIUS_KM = 0.15


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(radians, map(float, (lat1, lng1, lat2, lng2)))
    value = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lng2-lng1)/2)**2
    return 6371 * 2 * atan2(sqrt(value), sqrt(max(0, 1-value)))


def update_stop_progress(conn, bus, location, lat, lng, accuracy, recorded):
    if accuracy > 100:
        return
    stops = conn.execute("SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order", (bus["route_id"],)).fetchall()
    current = next((stop for stop in stops if stop["id"] == location["current_stop_id"]), None)
    sequence = current["sequence_order"] if current else -1
    ahead = [stop for stop in stops if stop["sequence_order"] > sequence and stop["latitude"] is not None and stop["longitude"] is not None]
    nearby = [(haversine_km(lat,lng,stop["latitude"],stop["longitude"]), stop) for stop in ahead]
    arrived = min(nearby, key=lambda pair: pair[0]) if nearby else None
    if arrived and arrived[0] <= GEOFENCE_RADIUS_KM:
        stop = arrived[1]
        following = next((item for item in stops if item["sequence_order"] > stop["sequence_order"]), None)
        final = following is None
        conn.execute("""UPDATE bus_locations SET current_stop_id=%s,next_stop_id=%s,distance_covered_km=%s,
                     status=%s,approach_notified_stop_id=NULL,college_entry_detected=%s,
                     college_entry_time=CASE WHEN %s THEN %s ELSE college_entry_time END WHERE bus_id=%s""",
                     (stop["id"], following["id"] if following else None, stop["distance_from_start_km"],
                      "reached_college" if final else "arrived_at_stop", final, final, recorded, bus["id"]))
        event = "college_entry" if final else "arrived_at_stop"
        notify(conn,bus,stop,event,f"{bus['bus_name']} arrived at {stop['stop_name']}.")
        return
    next_stop = next((stop for stop in stops if stop["id"] == location["next_stop_id"]), None)
    if next_stop and next_stop["latitude"] is not None and next_stop["longitude"] is not None:
        distance = haversine_km(lat,lng,next_stop["latitude"],next_stop["longitude"])
        if distance <= 1.5 and location.get("approach_notified_stop_id") != next_stop["id"]:
            conn.execute("UPDATE bus_locations SET approach_notified_stop_id=%s WHERE bus_id=%s", (next_stop["id"],bus["id"]))
            notify(conn,bus,next_stop,"approaching_stop",f"{bus['bus_name']} is approaching {next_stop['stop_name']}.")


def notify(conn,bus,stop,event,message):
    conn.execute("""INSERT INTO notifications(target_role,bus_id,message,event_type) VALUES ('admin',%s,%s,%s)""", (bus["id"],message,event))
    conn.execute("""INSERT INTO notifications(target_role,bus_id,student_id,message,event_type)
                 SELECT 'student',%s,student_id,%s,%s FROM student_bus_assignments WHERE bus_id=%s AND stop_id=%s""",
                 (bus["id"],message,event,bus["id"],stop["id"]))
