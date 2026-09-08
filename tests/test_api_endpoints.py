import unittest
import json
from app import create_app

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_auth_login_valid(self):
        res = self.client.post('/api/auth/login',
                               data=json.dumps({'email': 'admin@institution.edu', 'password': 'admin123'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('token', data)

    def test_stats_overview(self):
        res = self.client.get('/api/stats/overview')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('total_students', data['data'])

    def test_ai_assistant_query(self):
        res = self.client.post('/api/assistant/query',
                               data=json.dumps({'prompt': 'Who is absent today?'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('answer', data)

    def test_export_csv(self):
        res = self.client.get('/api/reports/export/csv')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, 'text/csv')
        self.assertIn(b'Face Recognition Attendance', res.data)

if __name__ == "__main__":
    unittest.main()
