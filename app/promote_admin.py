"""Explicit operator command for granting task-administrator access.

Run inside the API environment after creating the account:
    python -m app.promote_admin developer@example.com
"""
import argparse

from sqlalchemy import select

from app.database import SessionLocal
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant administrator access to an existing account.")
    parser.add_argument("email")
    email = parser.parse_args().email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            parser.error(f"No account exists for {email!r}; register it first.")
        if user.is_admin:
            print(f"{email} already has administrator access.")
            return
        user.is_admin = True
        db.commit()
        print(f"Administrator access granted to {email}.")


if __name__ == "__main__":
    main()
