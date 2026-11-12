import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ['SIMULATION_ENABLED'] = 'false'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import app
from routes.tracking import validate_fix


class TrackingTests(unittest.TestCase):
    def setUp(self):
        account_check = patch('routes.decorators.run_query',return_value={'id':1})
        account_check.start()
        self.addCleanup(account_check.stop)
        self.client = app.test_client()
        self.fix = dict(latitude=12.4, longitude=79.5, accuracy_m=12,
                        speed_kmph=30, trip_id=7, recorded_at=datetime.now(timezone.utc).isoformat())

    def driver(self):
        with self.client.session_transaction() as session:
            session.update(user_id=1, role='driver', driver_id=7, bus_id=99)

    def test_valid_fix(self):
        self.assertEqual(validate_fix(self.fix)[:4], (12.4, 79.5, 12, 30))

    def test_invalid_fixes(self):
        for key, value in [('latitude', 91), ('longitude', float('nan')), ('accuracy_m', -1),
                           ('speed_kmph', True), ('recorded_at', 'bad'),
                           ('recorded_at', (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat())]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_fix({**self.fix, key: value})

    def test_requires_driver(self):
        self.assertEqual(self.client.post('/api/drivers/location', json=self.fix).status_code, 401)
        with self.client.session_transaction() as session:
            session.update(user_id=2, role='student')
        self.assertEqual(self.client.post('/api/drivers/location', json=self.fix).status_code, 403)

    def test_cross_origin_rejected(self):
        self.driver()
        self.assertEqual(self.client.post('/api/drivers/location', json=self.fix,
                         headers={'Origin': 'https://attacker.example'}).status_code, 403)

    @patch('services.live_tracking.update_stop_progress')
    @patch('routes.tracking.get_connection')
    def test_ingestion_uses_current_database_assignment(self, connection, progress):
        self.driver()
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.side_effect = [{'bus_id': 2}, {'id':2,'route_id':1}, {'recorded_at': None,'active_trip_id':7}, {'started_at':datetime.now(timezone.utc)-timedelta(seconds=1)}]
        response = self.client.post('/api/drivers/location', json=self.fix)
        self.assertEqual(response.status_code, 200)
        calls = conn.execute.call_args_list
        self.assertEqual(calls[4].args[1][0], 2)
        self.assertEqual(calls[5].args[1][-1], 2)

    @patch('routes.tracking.get_connection')
    def test_out_of_order_fix_rejected(self, connection):
        self.driver()
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.side_effect = [{'bus_id': 2}, {'id':2}, {'recorded_at': datetime.now(timezone.utc),'active_trip_id':7}, {'started_at':datetime.now(timezone.utc)-timedelta(seconds=1)}]
        self.assertEqual(self.client.post('/api/drivers/location', json=self.fix).status_code, 409)
        self.assertEqual(conn.execute.call_count, 4)

    @patch('routes.buses.run_query', return_value=None)
    def test_unassigned_student_cannot_read_bus(self, query):
        with self.client.session_transaction() as session:
            session.update(user_id=2, role='student', student_id=1)
        self.assertEqual(self.client.get('/api/buses/2/location').status_code, 403)
        self.assertEqual(self.client.get('/api/buses').status_code, 403)

    def test_freshness(self):
        from routes.buses import annotate_location
        loc = dict(recorded_at=datetime.now(timezone.utc), sharing_active=True)
        annotate_location(loc)
        self.assertFalse(loc['is_stale'])
        loc = dict(recorded_at=datetime.now(timezone.utc)-timedelta(seconds=45), sharing_active=True)
        annotate_location(loc)
        self.assertTrue(loc['is_stale'])

class BoardingTests(unittest.TestCase):
    def setUp(self):
        account_check = patch('routes.decorators.run_query',return_value={'id':1})
        account_check.start()
        self.addCleanup(account_check.stop)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session.update(user_id=2, role='student', student_id=1)

    def test_students_cannot_generate_codes(self):
        self.assertEqual(self.client.get('/api/buses/1/qr-code-text').status_code, 403)
        self.assertEqual(self.client.get('/api/buses/1/qr').status_code, 403)

    def test_unsigned_boarding_code_rejected(self):
        response = self.client.post('/api/boarding', json={'qr_text': 'BUS-1-20261112'})
        self.assertEqual(response.status_code, 400)

    @patch('routes.attendance.get_connection')
    def test_boarding_uses_locked_bus_and_one_transaction(self, connection):
        from itsdangerous import URLSafeTimedSerializer
        from config import SECRET_KEY
        def _qr_code_for_bus(bus_id):
            return URLSafeTimedSerializer(SECRET_KEY,salt="bus-boarding").dumps({"bus_id":bus_id,"trip_id":7})
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.side_effect = [
            {'capacity': 50}, {'stop_id': 3}, {'id':7}, None, {'count': 4}
        ]
        response = self.client.post('/api/boarding', json={'qr_text': _qr_code_for_bus(1)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['passengers'], 5)
        self.assertIn('FOR UPDATE', conn.execute.call_args_list[0].args[0])
        connection.assert_called_once()

    @patch('routes.attendance.get_connection')
    def test_capacity_prevents_insert(self, connection):
        from itsdangerous import URLSafeTimedSerializer
        from config import SECRET_KEY
        def _qr_code_for_bus(bus_id):
            return URLSafeTimedSerializer(SECRET_KEY,salt="bus-boarding").dumps({"bus_id":bus_id,"trip_id":7})
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.side_effect = [
            {'capacity': 1}, {'stop_id': 3}, {'id':7}, None, {'count': 1}
        ]
        response = self.client.post('/api/boarding', json={'qr_text': _qr_code_for_bus(1)})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(conn.execute.call_count, 5)


if __name__ == '__main__':
    unittest.main()
