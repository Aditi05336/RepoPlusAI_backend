"""
test_auth.py

Integration test suite for RepoPulse AI authentication system.
Tests signup, duplicate checks, login, password verification, and JWT auth.
"""

import unittest
import uuid
from app import create_app
from auth.models import User, db
from auth.utils import decode_jwt_token


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Generate unique test user credentials
        uid = str(uuid.uuid4())[:8]
        self.test_name = f"Test User {uid}"
        self.test_email = f"user_{uid}@example.com"
        self.test_github = f"github-{uid}"
        self.test_password = "SecurePassword123!"

    def tearDown(self):
        # Clean up test user if created
        with self.app.app_context():
            user = User.query.filter_by(email=self.test_email).first()
            if user:
                db.session.delete(user)
                db.session.commit()
        self.app_context.pop()

    def test_01_signup_success(self):
        payload = {
            "name": self.test_name,
            "email": self.test_email,
            "github_username": self.test_github,
            "password": self.test_password,
        }
        res = self.client.post("/api/auth/signup", json=payload)
        data = res.get_json()

        self.assertEqual(res.status_code, 201)
        self.assertTrue(data.get("success"))
        self.assertIn("token", data)
        self.assertEqual(data["user"]["email"], self.test_email.lower())
        self.assertEqual(data["user"]["github_username"], self.test_github)

        # Verify token
        is_valid, token_data = decode_jwt_token(data["token"])
        self.assertTrue(is_valid)
        self.assertEqual(token_data["email"], self.test_email.lower())

    def test_02_duplicate_email(self):
        # Create initial user
        self.test_01_signup_success()

        # Try registering again with same email
        payload = {
            "name": "Another Name",
            "email": self.test_email,
            "github_username": f"different-{str(uuid.uuid4())[:5]}",
            "password": self.test_password,
        }
        res = self.client.post("/api/auth/signup", json=payload)
        data = res.get_json()

        self.assertEqual(res.status_code, 409)
        self.assertFalse(data.get("success"))

    def test_03_login_success(self):
        self.test_01_signup_success()

        payload = {
            "email": self.test_email,
            "password": self.test_password,
        }
        res = self.client.post("/api/auth/login", json=payload)
        data = res.get_json()

        self.assertEqual(res.status_code, 200)
        self.assertTrue(data.get("success"))
        self.assertIn("token", data)

    def test_04_login_invalid_password(self):
        self.test_01_signup_success()

        payload = {
            "email": self.test_email,
            "password": "WrongPassword999!",
        }
        res = self.client.post("/api/auth/login", json=payload)
        data = res.get_json()

        self.assertEqual(res.status_code, 401)
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("error"), "Invalid email or password.")

    def test_05_update_username_success(self):
        signup_res = self.client.post("/api/auth/signup", json={
            "name": self.test_name,
            "email": self.test_email,
            "github_username": self.test_github,
            "password": self.test_password,
        })
        token = signup_res.get_json()["token"]

        new_username = f"updated-{str(uuid.uuid4())[:5]}"
        res = self.client.put("/api/auth/username", json={"username": new_username}, headers={"Authorization": f"Bearer {token}"})
        data = res.get_json()

        self.assertEqual(res.status_code, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data["user"]["username"], new_username)
        self.assertEqual(data["user"]["github_username"], self.test_github)

    def test_06_update_username_unauthorized(self):
        res = self.client.put("/api/auth/username", json={"username": "unauthorized-user"})
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()

