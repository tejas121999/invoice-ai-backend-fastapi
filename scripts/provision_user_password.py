"""One-time administrative utility to set an existing user's password."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.repositories.user_repository import get_user_by_email


MINIMUM_PASSWORD_LENGTH = 12


class ProvisioningError(Exception):
    """Raised when a password cannot be safely provisioned."""


def _read_new_password() -> str:
    password = getpass.getpass("New password: ")
    confirmation = getpass.getpass("Confirm new password: ")
    if not password:
        raise ProvisioningError("Password must not be empty.")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ProvisioningError(
            f"Password must be at least {MINIMUM_PASSWORD_LENGTH} characters."
        )
    if password != confirmation:
        raise ProvisioningError("Password confirmation did not match.")
    return password


def provision_user_password(
    email: str,
    session_factory: Callable[[], Session] = SessionLocal,
    password_reader: Callable[[], str] = _read_new_password,
    confirmation_reader: Callable[[str], str] = input,
) -> None:
    normalized_email = email.strip()
    if not normalized_email:
        raise ProvisioningError("Email must not be empty.")

    db = session_factory()
    try:
        user = get_user_by_email(db, normalized_email)
        if user is None:
            raise ProvisioningError("No existing user was found for that email.")

        password = password_reader()
        print(f"About to update only the password hash for existing user ID {user.id}.")
        confirmation = confirmation_reader(
            "Commit this password update? Type 'YES' to continue: "
        )
        if confirmation != "YES":
            db.rollback()
            raise ProvisioningError("Password update cancelled; no changes were committed.")

        new_hash = hash_password(password)
        user.passwordHash = new_hash
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Securely provision a password for an existing user."
    )
    parser.add_argument("email", help="Email address of the existing user")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        provision_user_password(args.email)
    except ProvisioningError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("Error: Password update failed; transaction rolled back.", file=sys.stderr)
        return 1

    print("Password hash updated successfully for the existing user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
