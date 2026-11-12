ALTER TABLE bus_locations ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION CHECK (latitude BETWEEN -90 AND 90);
ALTER TABLE bus_locations ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION CHECK (longitude BETWEEN -180 AND 180);
ALTER TABLE bus_locations ADD COLUMN IF NOT EXISTS accuracy_m DOUBLE PRECISION;
ALTER TABLE bus_locations ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMPTZ;
ALTER TABLE bus_locations ADD COLUMN IF NOT EXISTS location_source TEXT NOT NULL DEFAULT 'simulation';
ALTER TABLE bus_locations ADD COLUMN IF NOT EXISTS sharing_active BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS gps_history (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 bus_id INTEGER NOT NULL REFERENCES buses(id),
 driver_id INTEGER NOT NULL REFERENCES drivers(id),
 latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
 longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
 accuracy_m DOUBLE PRECISION NOT NULL CHECK (accuracy_m >= 0),
 speed_kmph DOUBLE PRECISION NOT NULL CHECK (speed_kmph >= 0),
 recorded_at TIMESTAMPTZ NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(bus_id, recorded_at)
);
CREATE INDEX IF NOT EXISTS gps_history_bus_time_idx ON gps_history(bus_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS assignments_student_idx ON student_bus_assignments(student_id);
CREATE INDEX IF NOT EXISTS attendance_date_idx ON attendance(attendance_date);
CREATE INDEX IF NOT EXISTS notifications_bus_time_idx ON notifications(bus_id, created_at DESC);
