"""Grant or revoke reviewer access for an existing account.

Run inside the API environment:
    python -m app.promote_reviewer reviewer@example.com
    python -m app.promote_reviewer --revoke reviewer@example.com
"""
import argparse

from sqlalchemy import select

from app.database import SessionLocal
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or revoke reviewer access for an existing account.")
    parser.add_argument("--revoke", action="store_true", help="Remove reviewer access instead of granting it.")
    parser.add_argument("email")
    args = parser.parse_args()
    email = args.email.strip().lower()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            parser.error(f"No account exists for {email!r}; register it first.")
        desired = not args.revoke
        if user.is_reviewer == desired:
            print(f"{email} already has reviewer access." if desired else f"{email} is not a reviewer.")
            return
        user.is_reviewer = desired
        db.commit()
        print(f"Reviewer access {'granted to' if desired else 'revoked from'} {email}.")


if __name__ == "__main__":
    main()
