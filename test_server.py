import unittest
import json
from app import create_app

class TestAttendanceApp(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_index_route(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Face Recognition Attendance', res.data)

    def test_stats_route(self):
        res = self.client.get('/api/stats')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('total_registered', data)
        self.assertIn('total_today_attendance', data)

    def test_students_list(self):
        res = self.client.get('/api/students')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIsInstance(data['students'], list)

    def test_today_attendance(self):
        res = self.client.get('/api/attendance/today')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIsInstance(data['attendance'], list)

    def test_invalid_train_password(self):
        res = self.client.post('/api/train', 
                               data=json.dumps({'password': 'wrong_password'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 403)

if __name__ == '__main__':
    unittest.main()
