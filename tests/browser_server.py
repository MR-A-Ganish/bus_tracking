"""Disposable local browser review server. Shut down through /__test_shutdown."""
import os
os.environ['SIMULATION_ENABLED']='false'
os.environ['APP_ENV']='development'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from contextlib import ExitStack
from unittest.mock import patch
import uuid
import threading
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
from config import DATABASE_URL
from app import app
schema='bus_browser_'+uuid.uuid4().hex

def connect():
    return psycopg.connect(DATABASE_URL,row_factory=dict_row,options=f'-csearch_path={schema}',connect_timeout=10)

try:
    with psycopg.connect(DATABASE_URL,connect_timeout=10) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    with connect() as conn:
        root=Path(__file__).resolve().parents[1]
        conn.execute((root/'database/schema.postgresql.sql').read_text(encoding='utf-8'))
        for migration in sorted((root/'database/migrations').glob('*.sql')):
            conn.execute(migration.read_text(encoding='utf-8'))
        password=generate_password_hash('browser-test-password')
        for role in ['admin','driver','student']:
            user=conn.execute('INSERT INTO users(username,password,role) VALUES (%s,%s,%s) RETURNING id',(role+'-demo',password,role)).fetchone()
            if role=='driver':
                conn.execute("INSERT INTO drivers(user_id,name,bus_id) VALUES (%s,'Demo Driver',1)",(user['id'],))
            elif role=='admin':
                conn.execute("INSERT INTO admins(user_id,name) VALUES (%s,'Demo Admin')",(user['id'],))
            else:
                student=conn.execute("INSERT INTO students(user_id,name) VALUES (%s,'Demo Student') RETURNING id",(user['id'],)).fetchone()
                conn.execute('INSERT INTO student_bus_assignments(student_id,bus_id,stop_id) VALUES (%s,1,2)',(student['id'],))
    with ExitStack() as stack:
        test_pool = ConnectionPool(DATABASE_URL,min_size=0,max_size=5,timeout=10,open=True,
                                   kwargs={"row_factory":dict_row,"connect_timeout":10,"options":f"-csearch_path={schema}"})
        stack.callback(test_pool.close)
        stack.enter_context(patch('database._open_connection',test_pool.connection))
        server=make_server('127.0.0.1',5071,app,threaded=True)
        @app.post('/__test_shutdown')
        def shutdown():
            threading.Thread(target=server.shutdown,daemon=True).start()
            return 'Closing test server'
        print('Browser review ready at http://127.0.0.1:5071',flush=True)
        server.serve_forever()
finally:
    with psycopg.connect(DATABASE_URL,connect_timeout=10) as conn:
        conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
    print('Removed browser review schema',flush=True)
