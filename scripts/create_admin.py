"""Create or reset the SiteScout admin user. Run on the VPS only."""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import db, init_db
from app.security import hash_password


def main() -> None:
    init_db()
    username = input("Admin username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
    password = getpass.getpass("Password (min 12 characters, hidden): ")
    confirm = getpass.getpass("Repeat password: ")
    if password != confirm:
        print("Passwords do not match. Nothing was saved.")
        return
    if len(password) < 12:
        print("Password too short. Nothing was saved.")
        return
    with db() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?) "
            "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash",
            (username, hash_password(password)),
        )
    print(f"Admin user '{username}' saved.")


if __name__ == "__main__":
    main()
