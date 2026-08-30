-- ============================================================
-- Smart College Bus Tracking and Transportation Management System
-- MySQL Schema + Sample Data
-- ============================================================

DROP DATABASE IF EXISTS smart_bus_system;
CREATE DATABASE smart_bus_system;
USE smart_bus_system;

-- ------------------------------------------------------------
-- 1. USERS (login table for students, admins, and drivers)
-- ------------------------------------------------------------
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,   -- stored as a salted hash
    role ENUM('student', 'admin', 'driver') NOT NULL
);

-- ------------------------------------------------------------
-- 2. ROUTES
-- ------------------------------------------------------------
CREATE TABLE routes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    route_name VARCHAR(100) NOT NULL,
    start_point VARCHAR(100) NOT NULL,
    end_point VARCHAR(100) NOT NULL
);

-- ------------------------------------------------------------
-- 3. BUS STOPS (ordered stops along a route)
-- ------------------------------------------------------------
CREATE TABLE bus_stops (
    id INT AUTO_INCREMENT PRIMARY KEY,
    route_id INT NOT NULL,
    stop_name VARCHAR(100) NOT NULL,
    sequence_order INT NOT NULL,              -- 0 = start, increasing towards college
    distance_from_start_km FLOAT NOT NULL,     -- cumulative distance from route start
    latitude FLOAT DEFAULT NULL,               -- used to plot the live tracking map
    longitude FLOAT DEFAULT NULL,
    FOREIGN KEY (route_id) REFERENCES routes(id)
);

-- ------------------------------------------------------------
-- 4. BUSES
-- ------------------------------------------------------------
CREATE TABLE buses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bus_name VARCHAR(50) NOT NULL,
    driver_name VARCHAR(100) DEFAULT NULL,
    capacity INT NOT NULL DEFAULT 50,
    current_passengers INT NOT NULL DEFAULT 0,
    route_id INT NOT NULL,
    FOREIGN KEY (route_id) REFERENCES routes(id)
);

-- ------------------------------------------------------------
-- 5. STUDENTS
-- ------------------------------------------------------------
CREATE TABLE students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    register_no VARCHAR(50) DEFAULT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ------------------------------------------------------------
-- 6. ADMINS
-- ------------------------------------------------------------
CREATE TABLE admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ------------------------------------------------------------
-- 6b. DRIVERS (one real GPS-sharing account per bus)
-- ------------------------------------------------------------
CREATE TABLE drivers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    license_no VARCHAR(50) DEFAULT NULL,
    bus_id INT DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (bus_id) REFERENCES buses(id)
);

-- ------------------------------------------------------------
-- 7. STUDENT <-> BUS/STOP ASSIGNMENT
-- ------------------------------------------------------------
CREATE TABLE student_bus_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    bus_id INT NOT NULL,
    stop_id INT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (bus_id) REFERENCES buses(id),
    FOREIGN KEY (stop_id) REFERENCES bus_stops(id)
);

-- ------------------------------------------------------------
-- 8. BUS LOCATIONS (one row per bus; either driven by the simulated
--    background thread, or by real GPS pings from a logged-in driver -
--    see gps_* columns. gps_updated_at recency is what decides which
--    source is authoritative at read time: see services/geofence.py
--    is_gps_live() and routes/buses.py.)
-- ------------------------------------------------------------
CREATE TABLE bus_locations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bus_id INT NOT NULL UNIQUE,
    distance_covered_km FLOAT NOT NULL DEFAULT 0,
    current_stop_id INT DEFAULT NULL,
    next_stop_id INT DEFAULT NULL,
    status ENUM('not_started','moving','arrived_at_stop','waiting','reached_college') NOT NULL DEFAULT 'not_started',
    traffic_condition ENUM('low','medium','high') NOT NULL DEFAULT 'low',
    speed_kmph FLOAT NOT NULL DEFAULT 30,
    college_entry_detected TINYINT(1) NOT NULL DEFAULT 0,
    college_entry_time DATETIME DEFAULT NULL,
    gps_lat FLOAT DEFAULT NULL,           -- real GPS latitude from the driver's device
    gps_lng FLOAT DEFAULT NULL,           -- real GPS longitude from the driver's device
    gps_accuracy_m FLOAT DEFAULT NULL,    -- accuracy radius (metres) reported by the Geolocation API
    gps_speed_kmph FLOAT DEFAULT NULL,    -- real speed reported by the Geolocation API, if available
    gps_updated_at DATETIME DEFAULT NULL, -- last time a real GPS ping was received for this bus
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (bus_id) REFERENCES buses(id),
    FOREIGN KEY (current_stop_id) REFERENCES bus_stops(id),
    FOREIGN KEY (next_stop_id) REFERENCES bus_stops(id)
);

-- ------------------------------------------------------------
-- 9. ATTENDANCE (QR boarding records)
-- ------------------------------------------------------------
CREATE TABLE attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    bus_id INT NOT NULL,
    stop_id INT NOT NULL,
    attendance_date DATE NOT NULL,
    attendance_time TIME NOT NULL,
    boarding_status ENUM('boarded') NOT NULL DEFAULT 'boarded',
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (bus_id) REFERENCES buses(id),
    FOREIGN KEY (stop_id) REFERENCES bus_stops(id),
    UNIQUE KEY unique_daily_boarding (student_id, bus_id, attendance_date)
);

-- ------------------------------------------------------------
-- 10. NOTIFICATIONS
-- ------------------------------------------------------------
CREATE TABLE notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    target_role ENUM('student','admin','all') NOT NULL DEFAULT 'all',
    bus_id INT DEFAULT NULL,
    student_id INT DEFAULT NULL,
    message VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bus_id) REFERENCES buses(id)
);

-- ------------------------------------------------------------
-- 11. ETA PREDICTIONS (log of what the ML model predicted)
-- ------------------------------------------------------------
CREATE TABLE eta_predictions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bus_id INT NOT NULL,
    stop_id INT NOT NULL,
    predicted_eta_minutes FLOAT NOT NULL,
    distance_km FLOAT NOT NULL,
    traffic_condition VARCHAR(20) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bus_id) REFERENCES buses(id),
    FOREIGN KEY (stop_id) REFERENCES bus_stops(id)
);

-- ============================================================
-- SAMPLE DATA
-- ============================================================

INSERT INTO routes (route_name, start_point, end_point) VALUES
('Vadalur - IFET College Route', 'Vadalur', 'IFET College');

-- Stops in order, with approximate cumulative distance in km, and
-- approximate lat/lng along the Vadalur -> IFET College corridor
-- (used to draw the live tracking map / seed the simulated fallback;
-- positions are indicative for this prototype, not surveyed GPS
-- coordinates - see README section 9). TODO: replace with the real
-- named stops along this route.
INSERT INTO bus_stops (route_id, stop_name, sequence_order, distance_from_start_km, latitude, longitude) VALUES
(1, 'Vadalur',       0, 0,    11.4544, 79.3900),
(1, 'IFET College',  1, 22.0, 11.8628, 79.5643);

INSERT INTO buses (bus_name, driver_name, capacity, current_passengers, route_id) VALUES
('Bus 01', 'Mr. Raja', 50, 0, 1),
('Bus 02', 'Mr. Selvam', 45, 0, 1);

INSERT INTO bus_locations (bus_id, distance_covered_km, current_stop_id, next_stop_id, status, traffic_condition, speed_kmph)
VALUES
(1, 0, 1, 2, 'not_started', 'low', 30),
(2, 0, 1, 2, 'not_started', 'low', 30);

-- Demo users
-- Passwords below are placeholders; the backend re-hashes and stores real
-- hashes for 'student01'/'1234' and 'admin01'/'admin123' on first run via seed_demo_users.py
-- (kept here only as documentation of the demo credentials)
-- username: student01 / password: 1234   (role = student)
-- username: student02 / password: 1234   (role = student)
-- username: admin01   / password: admin123 (role = admin)

-- Sample student->bus->stop assignment (created after seeding users, see backend/seed.py)
