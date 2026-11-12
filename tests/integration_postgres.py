"""Exercise real PostgreSQL APIs in a disposable, isolated schema."""
import os
os.environ['SIMULATION_ENABLED'] = 'false'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import uuid
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from werkzeug.security import generate_password_hash
from config import DATABASE_URL, SECRET_KEY
from app import app
from itsdangerous import URLSafeTimedSerializer

original_error_handler = app.error_handler_spec[None][None][psycopg.OperationalError]
def diagnose_database_error(error):
    print('Database test failure',type(error).__name__,str(error),flush=True)
    return original_error_handler(error)
app.error_handler_spec[None][None][psycopg.OperationalError] = diagnose_database_error

schema = 'bus_test_'  + uuid.uuid4().hex

def connect():
    for attempt in range(3):
        try:
            return psycopg.connect(DATABASE_URL,row_factory=dict_row,options=f'-csearch_path={schema}',connect_timeout=10)
        except psycopg.OperationalError:
            if attempt == 2:
                raise
            print('Retrying an isolated test database connection',flush=True)
            time.sleep(0.5)

def client_for(role, profile_id=1):
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(user_id={"admin":1,"driver":2,"student":profile_id+2}[role],role=role)
        session[role+'_id'] = profile_id
    return client

def expect(response,status=200):
    assert response.status_code == status, (response.status_code,response.get_json())
    return response.get_json()

try:
    with psycopg.connect(DATABASE_URL,connect_timeout=10) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    with connect() as conn:
        root = Path(__file__).resolve().parents[1]
        conn.execute((root/'database/schema.postgresql.sql').read_text(encoding='utf-8'))
        for migration in sorted((root/'database/migrations').glob('*.sql')):
            conn.execute(migration.read_text(encoding='utf-8'))
        password = generate_password_hash('integration-test-password')
        for username,role in [('admin','admin'),('driver','driver'),('student1','student'),('student2','student')]:
            user = conn.execute('INSERT INTO users(username,password,role) VALUES (%s,%s,%s) RETURNING id',(username,password,role)).fetchone()
            if role == 'admin':
                conn.execute('INSERT INTO admins(user_id,name) VALUES (%s,%s)',(user['id'],'Test Admin'))
            elif role == 'driver':
                conn.execute('INSERT INTO drivers(user_id,name,bus_id) VALUES (%s,%s,1)',(user['id'],'Test Driver'))
            else:
                student = conn.execute('INSERT INTO students(user_id,name) VALUES (%s,%s) RETURNING id',(user['id'],username)).fetchone()
                conn.execute('INSERT INTO student_bus_assignments(student_id,bus_id,stop_id) VALUES (%s,1,2)',(student['id'],))
    with ExitStack() as stack:
        test_pool = ConnectionPool(DATABASE_URL,min_size=0,max_size=5,timeout=10,open=True,
                                   kwargs={"row_factory":dict_row,"connect_timeout":10,"options":f"-csearch_path={schema}"})
        stack.callback(test_pool.close)
        stack.enter_context(patch('database._open_connection',test_pool.connection))
        admin,driver,student = client_for('admin'),client_for('driver'),client_for('student')
        for page in ['/','/admin.html','/student.html','/driver.html','/register.html']:
            assert admin.get(page).status_code == 200
        expect(admin.get('/api/admin/lookup'))
        expect(admin.get('/api/admin/drivers'))
        expect(admin.get('/api/admin/admins'))
        expect(admin.get('/api/students'))
        expect(student.get('/api/buses/2/location'),403)
        trip = expect(driver.post('/api/driver/start-trip'))['trip_id']
        assert expect(driver.post('/api/driver/start-trip'))['trip_id'] == trip
        expect(driver.get('/api/driver/me'))
        fix = dict(latitude=11.9279,longitude=79.4614,accuracy_m=10,speed_kmph=25,
                   recorded_at=datetime.now(timezone.utc).isoformat(),trip_id=trip)
        expect(driver.post('/api/driver/location',json=fix))
        location = expect(student.get('/api/buses/1/location'))['location']
        assert location['is_live'] and location['current_stop_id'] == 2
        expect(driver.post('/api/driver/location',json=fix),409)
        assert driver.get('/api/buses/1/qr').status_code == 200
        code = expect(driver.get('/api/buses/1/qr-code-text'))['qr_text']
        expect(student.post('/api/boarding',json={'qr_text':code}))
        expect(student.post('/api/boarding',json={'qr_text':code}),409)
        expect(admin.get('/api/attendance'))
        expect(student.get('/api/notifications'))
        with connect() as conn:
            conn.execute('UPDATE bus_locations SET recorded_at=CURRENT_TIMESTAMP-INTERVAL \'1 minute\' WHERE bus_id=1')
        location = expect(student.get('/api/buses/1/location'))['location']
        assert not location['is_live'] and location['lat'] == fix['latitude']
        expect(driver.post('/api/driver/end-trip',json={'trip_id':trip}))
        expect(student.post('/api/boarding',json={'qr_text':code}),409)
        new_trip = expect(driver.post('/api/driver/start-trip'))['trip_id']
        assert new_trip != trip
        with connect() as conn:
            conn.execute('UPDATE buses SET capacity=1 WHERE id=1')
        code = expect(driver.get('/api/buses/1/qr-code-text'))['qr_text']
        def board(student_id):
            return client_for('student',student_id).post('/api/boarding',json={'qr_text':code}).status_code
        statuses = list(ThreadPoolExecutor(max_workers=2).map(board,[1,2]))
        assert sorted(statuses) == [200,409], statuses
        with connect() as conn:
            bus = conn.execute('SELECT current_passengers FROM buses WHERE id=1').fetchone()
            assert bus['current_passengers'] == 1
            assert conn.execute('SELECT COUNT(*) AS c FROM attendance WHERE trip_id=%s',(new_trip,)).fetchone()['c'] == 1
        # Failed admin creation must roll back the preceding user insert too.
        response = admin.post('/api/admin/drivers',json=dict(username='duplicate_driver',password='a-long-test-password',name='Test',bus_id=1))
        expect(response,409)
        with connect() as conn:
            assert not conn.execute("SELECT id FROM users WHERE username='duplicate_driver'").fetchone()
        # The assignment trigger rejects mismatched route data in the same transaction.
        with connect() as conn:
            conn.execute("INSERT INTO routes(id,route_name,start_point,end_point) VALUES (3,'Other','A','B')")
            conn.execute("INSERT INTO bus_stops(id,route_id,stop_name,sequence_order,distance_from_start_km) VALUES (99,3,'Other stop',0,0)")
        response = admin.post('/api/admin/students',json=dict(username='invalid_route',password='a-long-test-password',name='Test',bus_id=1,stop_id=99))
        expect(response,409)
        with connect() as conn:
            assert not conn.execute("SELECT id FROM users WHERE username='invalid_route'").fetchone()
        expect(admin.put('/api/admin/stops/2',json={'stop_name':'Verified test stop','latitude':11.9279,'longitude':79.4614}))
        expect(student.put('/api/admin/stops/2',json={'stop_name':'Invalid','latitude':0,'longitude':0}),403)
        expect(admin.put('/api/admin/stops/2',json={'stop_name':'Invalid','latitude':91,'longitude':0}),400)
        expect(admin.post('/api/admin/buses/1/end-trip',json={'trip_id':new_trip}))
        expect(driver.post('/api/driver/location',json={**fix,'trip_id':new_trip,'recorded_at':datetime.now(timezone.utc).isoformat()}),409)
        with connect() as conn:
            route_id=conn.execute("SELECT id FROM routes WHERE route_name='Vadalur to IFET College'").fetchone()['id']
            rows=conn.execute('SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order',(route_id,)).fetchall()
        def route_payload(rows):
            return [dict(id=row['id'],stop_name=row['stop_name'],latitude=float(row['latitude']),longitude=float(row['longitude']),distance_from_start_km=float(row['distance_from_start_km'])) for row in rows]
        route_stops=route_payload(rows)
        route_stops.insert(1,dict(id=None,stop_name='Admin pickup',latitude=11.75,longitude=79.6,distance_from_start_km=25))
        expect(admin.put(f'/api/admin/routes/{route_id}/stops',json={'stops':route_stops}))
        with connect() as conn:
            rows=conn.execute('SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order',(route_id,)).fetchall()
        assert len(rows)==3 and rows[1]['stop_name']=='Admin pickup'
        route_stops=route_payload(rows)
        expect(admin.put('/api/admin/buses/2',json={'route_id':route_id}))
        assert not expect(admin.get('/api/route-optimize?bus_id=2'))['success']
        expect(admin.put('/api/admin/buses/1',json={'route_id':route_id}),409)
        expect(admin.put('/api/admin/buses/1',json={'route_id':route_id,'reset_assignments':True}))
        assignment=expect(student.get('/api/students/me'))['assignment']
        assert assignment['route_id']==route_id and assignment['stop_id']==route_stops[0]['id']
        vadalur_trip=expect(driver.post('/api/driver/start-trip'))['trip_id']
        expect(admin.put(f'/api/admin/routes/{route_id}/stops',json={'stops':route_stops}),409)
        expect(admin.put('/api/admin/buses/1',json={'route_id':1,'reset_assignments':True}),409)
        expect(driver.post('/api/driver/end-trip',json={'trip_id':vadalur_trip}))
        removed_origin=[dict(stop) for stop in route_stops[1:]]
        removed_origin[0]['distance_from_start_km']=0
        expect(admin.put(f'/api/admin/routes/{route_id}/stops',json={'stops':removed_origin}),409)
        print('PASS: Vadalur route, admin pickup stops, bus-route assignment, explicit student remapping, active-trip guards and referenced-stop protection',flush=True)
        login_client=app.test_client()
        expect(login_client.post('/api/login',json={'username':'driver','password':'integration-test-password'}))
        expect(login_client.get('/api/driver/me'))
        print('PASS: migrations, all dashboards, management APIs, real login, GPS and geofence, ownership, stale GPS, signed QR, duplicate boarding, repeat trips, concurrent capacity and rollback',flush=True)
finally:
    with psycopg.connect(DATABASE_URL,connect_timeout=10) as conn:
        conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
    print('Removed the isolated test schema',flush=True)
