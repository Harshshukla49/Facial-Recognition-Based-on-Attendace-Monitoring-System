import unittest
import json
from app import create_app
from core.database import Database

class TestKioskAttendanceIntegration(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_kiosk_view_route(self):
        res = self.client.get('/kiosk')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Autonomous Attendance Kiosk', res.data)
        self.assertIn(b'LOOK AT THE CAMERA', res.data)

    def test_kiosks_list_api(self):
        res = self.client.get('/api/kiosks')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIsInstance(data['kiosks'], list)

    def test_recognition_events_api(self):
        res = self.client.get('/api/recognition_events')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIsInstance(data['events'], list)

if __name__ == '__main__':
    unittest.main()
