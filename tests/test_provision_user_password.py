import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import verify_password
from app.models.user import User
from scripts.provision_user_password import (
    MINIMUM_PASSWORD_LENGTH,
    ProvisioningError,
    _read_new_password,
    provision_user_password,
)


class ProvisionUserPasswordTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        User.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        self.user = User(
            name="Existing Admin",
            email="admin@example.test",
            passwordHash="existing-invalid-hash",
            role="admin",
            createdAt=datetime(2026, 1, 1, 12, 0),
            updatedAt=datetime(2026, 1, 2, 12, 0),
        )
        db.add(self.user)
        db.commit()
        self.user_id = self.user.id
        self.original_values = {
            "id": self.user.id,
            "name": self.user.name,
            "email": self.user.email,
            "role": self.user.role,
            "createdAt": self.user.createdAt,
            "updatedAt": self.user.updatedAt,
        }
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def get_user(self) -> User:
        db = self.Session()
        user = db.query(User).filter(User.id == self.user_id).one()
        db.expunge(user)
        db.close()
        return user

    def test_updates_only_password_hash_after_explicit_confirmation(self):
        password = "isolated-new-password"
        output = io.StringIO()

        with redirect_stdout(output):
            provision_user_password(
                self.original_values["email"],
                session_factory=self.Session,
                password_reader=lambda: password,
                confirmation_reader=lambda _: "YES",
            )

        updated = self.get_user()
        self.assertTrue(verify_password(password, updated.passwordHash))
        self.assertNotEqual(updated.passwordHash, "existing-invalid-hash")
        for field, expected in self.original_values.items():
            self.assertEqual(getattr(updated, field), expected, field)
        rendered_output = output.getvalue()
        self.assertNotIn(password, rendered_output)
        self.assertNotIn(updated.passwordHash, rendered_output)

    def test_missing_user_fails_without_creating_or_prompting(self):
        password_reader = Mock()
        confirmation_reader = Mock()

        with self.assertRaisesRegex(ProvisioningError, "No existing user"):
            provision_user_password(
                "missing@example.test",
                session_factory=self.Session,
                password_reader=password_reader,
                confirmation_reader=confirmation_reader,
            )

        password_reader.assert_not_called()
        confirmation_reader.assert_not_called()
        db = self.Session()
        self.assertEqual(db.query(User).count(), 1)
        self.assertEqual(
            db.query(User).filter(User.id == self.user_id).one().passwordHash,
            "existing-invalid-hash",
        )
        db.close()

    def test_cancellation_rolls_back_without_changing_password(self):
        with self.assertRaisesRegex(ProvisioningError, "cancelled"):
            provision_user_password(
                self.original_values["email"],
                session_factory=self.Session,
                password_reader=lambda: "isolated-new-password",
                confirmation_reader=lambda _: "NO",
            )

        self.assertEqual(self.get_user().passwordHash, "existing-invalid-hash")

    def test_hashing_error_rolls_back_without_changing_password(self):
        with patch(
            "scripts.provision_user_password.hash_password",
            side_effect=RuntimeError("hash failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "hash failure"):
                provision_user_password(
                    self.original_values["email"],
                    session_factory=self.Session,
                    password_reader=lambda: "isolated-new-password",
                    confirmation_reader=lambda _: "YES",
                )

        self.assertEqual(self.get_user().passwordHash, "existing-invalid-hash")

    def test_empty_email_is_rejected_before_opening_session(self):
        session_factory = Mock()

        with self.assertRaisesRegex(ProvisioningError, "Email must not be empty"):
            provision_user_password(
                "  ",
                session_factory=session_factory,
            )

        session_factory.assert_not_called()


class PasswordPromptTests(unittest.TestCase):
    def test_password_is_prompted_without_echo_and_confirmed(self):
        password = "x" * MINIMUM_PASSWORD_LENGTH
        with patch(
            "scripts.provision_user_password.getpass.getpass",
            side_effect=[password, password],
        ):
            self.assertEqual(_read_new_password(), password)

    def test_empty_short_and_mismatched_passwords_are_rejected(self):
        cases = [
            (["", ""], "must not be empty"),
            (["short", "short"], "at least"),
            (["a" * MINIMUM_PASSWORD_LENGTH, "different-password"], "did not match"),
        ]
        for responses, message in cases:
            with self.subTest(message=message):
                with patch(
                    "scripts.provision_user_password.getpass.getpass",
                    side_effect=responses,
                ):
                    with self.assertRaisesRegex(ProvisioningError, message):
                        _read_new_password()
