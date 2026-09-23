import unittest

import app as app_module


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config['TESTING'] = True
        self.client = app_module.app.test_client()
        app_module.reset_auth_store()

    def test_signup_and_login_user(self):
        response = self.client.post('/api/auth/signup', json={
            'name': 'Test User',
            'email': 'testuser@example.com',
            'phone': '+91 99999 11111',
            'username': 'testuser',
            'password': 'secret123',
            'role': 'user',
        })
        self.assertEqual(response.status_code, 201)

        login = self.client.post('/api/auth/login', json={
            'identifier': 'testuser@example.com',
            'password': 'secret123',
        })
        self.assertEqual(login.status_code, 200)
        payload = login.get_json()
        self.assertEqual(payload['user']['role'], 'user')
        self.assertIn('email', payload['user'])

    def test_admin_login_by_phone_and_user_trace(self):
        self.client.post('/api/auth/signup', json={
            'name': 'Admin User',
            'email': 'admin@example.com',
            'phone': '+91 77777 44444',
            'username': 'adminx',
            'password': 'adminpass',
            'role': 'admin',
        })

        login = self.client.post('/api/auth/login', json={
            'identifier': '+91 77777 44444',
            'password': 'adminpass',
        })
        self.assertEqual(login.status_code, 200)

        session = self.client.get('/api/auth/me')
        self.assertEqual(session.status_code, 200)

        location = self.client.post('/api/user/location', json={
            'lat': 12.9716,
            'lon': 77.5946,
            'status': 'Live',
        })
        self.assertEqual(location.status_code, 200)

        admin_users = self.client.get('/api/admin/users')
        self.assertEqual(admin_users.status_code, 200)
        data = admin_users.get_json()
        self.assertGreaterEqual(len(data['users']), 1)


if __name__ == '__main__':
    unittest.main()
