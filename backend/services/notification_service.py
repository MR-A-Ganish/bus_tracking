"""
Creates notification rows in the database in response to real system events
(bus starting, approaching a stop, arriving, boarding, delays, college
entry, capacity warnings). Nothing here is static placeholder text - every
call site passes in the actual bus/stop/student involved.
"""

from database import run_query


def create_notification(target_role, message, event_type, bus_id=None, student_id=None):
    run_query(
        """INSERT INTO notifications (target_role, bus_id, student_id, message, event_type)
           VALUES (%s, %s, %s, %s, %s)""",
        (target_role, bus_id, student_id, message, event_type),
        commit=True,
    )


def get_notifications(target_role, bus_id=None, student_id=None, limit=30):
    query = """SELECT * FROM notifications
               WHERE (target_role = %s OR target_role = 'all')"""
    params = [target_role]
    if bus_id is not None:
        query += " AND (bus_id = %s OR bus_id IS NULL)"
        params.append(bus_id)
    if student_id is not None:
        query += " AND (student_id = %s OR student_id IS NULL)"
        params.append(student_id)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    return run_query(query, tuple(params), fetch=True)
