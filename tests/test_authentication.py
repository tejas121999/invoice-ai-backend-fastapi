import unittest
from datetime import timedelta
from unittest.mock import patch

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_access_token,
    verify_password,
)
from app.models.user import User
from app.routers import auth_router


TEST_SECRET = "authentication-test-secret-key-32-characters"
OTHER_SECRET = "different-test-secret-key-32-characters"


class PasswordSecurityTests(unittest.TestCase):
    def test_password_hashing_and_verification(self):
        password = "correct horse battery staple"

        password_hash = hash_password(password)

        self.assertNotEqual(password_hash, password)
        self.assertTrue(verify_password(password, password_hash))

    def test_incorrect_password_is_rejected(self):
        password_hash = hash_password("right-password")

        self.assertFalse(verify_password("wrong-password", password_hash))
        self.assertFalse(verify_password("right-password", "not-an-argon2-hash"))


class JwtSecurityTests(unittest.TestCase):
    def setUp(self):
        self.secret_patch = patch.object(
            settings, "JWT_SECRET_KEY", SecretStr(TEST_SECRET)
        )
        self.secret_patch.start()

    def tearDown(self):
        self.secret_patch.stop()

    def test_access_token_contains_expected_claims(self):
        token = create_access_token(42)
        payload = verify_access_token(token)

        self.assertEqual(payload["sub"], "42")
        self.assertIn("iat", payload)
        self.assertIn("exp", payload)
        self.assertGreater(payload["exp"], payload["iat"])

    def test_valid_token_is_verified(self):
        token = create_access_token(7)

        self.assertEqual(verify_access_token(token)["sub"], "7")

    def test_expired_token_is_rejected(self):
        token = create_access_token(7, expires_delta=timedelta(seconds=-1))

        with self.assertRaises(jwt.ExpiredSignatureError):
            verify_access_token(token)

    def test_invalid_signature_is_rejected(self):
        token = create_access_token(7)

        with patch.object(settings, "JWT_SECRET_KEY", SecretStr(OTHER_SECRET)):
            with self.assertRaises(jwt.InvalidSignatureError):
                verify_access_token(token)

    def test_malformed_token_is_rejected(self):
        with self.assertRaises(jwt.InvalidTokenError):
            verify_access_token("not-a-jwt")


class AuthenticationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "test-password"
        cls.password_hash = hash_password(cls.password)

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        User.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            name="Test Operator",
            email="operator@example.com",
            passwordHash=self.password_hash,
            role="operator",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        app = FastAPI()
        app.include_router(auth_router.router)

        @app.get("/protected")
        def protected(current_user: User = Depends(get_current_user)):
            return {"user_id": current_user.id}

        @app.get("/role-protected")
        def role_protected(current_user: User = Depends(require_roles("admin"))):
            return {"user_id": current_user.id}

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.secret_patch = patch.object(
            settings, "JWT_SECRET_KEY", SecretStr(TEST_SECRET)
        )
        self.secret_patch.start()

    def tearDown(self):
        self.secret_patch.stop()
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def test_successful_login(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": self.user.email, "password": self.password},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["token_type"], "bearer")
        self.assertEqual(payload["expires_in"], settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        self.assertNotIn("password", payload)
        self.assertNotIn("passwordHash", payload)
        self.assertEqual(
            verify_access_token(payload["access_token"])["sub"],
            str(self.user.id),
        )

    def test_invalid_email_is_rejected_generically(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": self.password},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid email or password")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_invalid_password_is_rejected_generically(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": self.user.email, "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid email or password")

    def test_missing_bearer_token_is_rejected(self):
        response = self.client.get("/protected")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_non_existent_user_referenced_by_valid_token_is_rejected(self):
        token = create_access_token(999999)

        response = self.client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_role_check_rejects_user_without_required_role(self):
        token = create_access_token(self.user.id)

        response = self.client.get(
            "/role-protected",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 403)

    def test_role_check_accepts_user_with_required_role(self):
        self.user.role = "admin"
        self.db.commit()
        token = create_access_token(self.user.id)

        response = self.client.get(
            "/role-protected",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], self.user.id)
