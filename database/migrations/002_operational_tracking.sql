ALTER TABLE drivers ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS license_no VARCHAR(50);
ALTER TABLE drivers ALTER COLUMN bus_id DROP NOT NULL;
ALTER TABLE bus_locations ALTER COLUMN college_entry_detected DROP DEFAULT;
ALTER TABLE bus_locations ALTER COLUMN college_entry_detected TYPE BOOLEAN USING college_entry_detected::integer::boolean;
ALTER TABLE bus_locations ALTER COLUMN college_entry_detected SET DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS bus_trips (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 bus_id INTEGER NOT NULL REFERENCES buses(id),
 driver_id INTEGER REFERENCES drivers(id) ON DELETE SET NULL,
 started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 ended_at TIMESTAMPTZ,
 CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_trip_per_bus ON bus_trips(bus_id) WHERE ended_at IS NULL;
ALTER TABLE bus_locations ADD COLUMN IF NOT EXISTS active_trip_id BIGINT REFERENCES bus_trips(id);
ALTER TABLE bus_locations ADD COLUMN IF NOT EXISTS approach_notified_stop_id INTEGER REFERENCES bus_stops(id);
ALTER TABLE gps_history ADD COLUMN IF NOT EXISTS trip_id BIGINT REFERENCES bus_trips(id);
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS trip_id BIGINT REFERENCES bus_trips(id);
ALTER TABLE attendance DROP CONSTRAINT IF EXISTS attendance_student_id_bus_id_attendance_date_key;
CREATE UNIQUE INDEX IF NOT EXISTS attendance_student_trip_unique ON attendance(student_id,trip_id) WHERE trip_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS attendance_legacy_daily_unique ON attendance(student_id,bus_id,attendance_date) WHERE trip_id IS NULL;
CREATE INDEX IF NOT EXISTS attendance_trip_idx ON attendance(trip_id);
-- Adopt existing live coordinates during upgrade from the deployed application.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='bus_locations' AND column_name='gps_lat') THEN
  EXECUTE 'UPDATE bus_locations SET latitude=gps_lat,longitude=gps_lng,accuracy_m=gps_accuracy_m,
           recorded_at=gps_updated_at AT TIME ZONE ''UTC'',location_source=''gps'',sharing_active=FALSE
           WHERE recorded_at IS NULL AND gps_lat IS NOT NULL';
 END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS one_assignment_per_student ON student_bus_assignments(student_id);
CREATE UNIQUE INDEX IF NOT EXISTS one_driver_per_bus ON drivers(bus_id) WHERE bus_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS driver_user_unique ON drivers(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS student_user_unique ON students(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS admin_user_unique ON admins(user_id);
CREATE OR REPLACE FUNCTION validate_bus_assignment() RETURNS TRIGGER AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM buses b JOIN bus_stops s ON s.route_id=b.route_id WHERE b.id=NEW.bus_id AND s.id=NEW.stop_id) THEN
  RAISE EXCEPTION 'Stop must belong to assigned bus route' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS assignment_route_check ON student_bus_assignments;
CREATE TRIGGER assignment_route_check BEFORE INSERT OR UPDATE ON student_bus_assignments
 FOR EACH ROW EXECUTE FUNCTION validate_bus_assignment();
ALTER TABLE buses ADD CONSTRAINT buses_capacity_positive CHECK (capacity BETWEEN 1 AND 200) NOT VALID;
ALTER TABLE buses ADD CONSTRAINT buses_passenger_bounds CHECK (current_passengers BETWEEN 0 AND capacity) NOT VALID;
