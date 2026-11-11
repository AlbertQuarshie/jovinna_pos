"""Reset a Jovinna POS login password (for when the admin password is forgotten).

Run from the project folder. Close the POS app first.
  .venv\\Scripts\\python.exe tools\\reset_password.py              # the development copy (data folder)
  .venv\\Scripts\\python.exe tools\\reset_password.py --installed  # the installed app (AppData\\Local\\JovinnaPOS)

Anyone who can run this on the computer can reset passwords, as with any desktop app's local data;
keep the shop computer's Windows account protected with its own password.
"""
import getpass
import os
import sys
from pathlib import Path

if "--installed" in sys.argv:
    os.environ["JOVINNA_DATA_DIR"] = str(Path(os.environ["LOCALAPPDATA"]) / "JovinnaPOS")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402

if not config.DB_PATH.exists():
    sys.exit(f"No database found at {config.DB_PATH}")

from app.services import auth_service as auth  # noqa: E402


def main() -> int:
    users = auth.list_users()
    print(f"Database: {config.DB_PATH}\n")
    for i, u in enumerate(users, start=1):
        print(f"  {i}. {u.username:<15} {u.full_name:<25} {u.role:<8} {'active' if u.is_active else 'disabled'}")
    choice = input("\nNumber of the account to reset (Enter to cancel): ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(users):
        print("Cancelled. Nothing was changed.")
        return 1
    user = users[int(choice) - 1]
    first = getpass.getpass(f"New password for {user.username} (typing is hidden): ")
    if getpass.getpass("Type it again: ") != first:
        print("The passwords didn't match. Nothing was changed.")
        return 1
    try:
        auth.set_password(user.id, first)
        if not user.is_active:
            auth.update_user(user.id, full_name=user.full_name, role=user.role, is_active=True)
    except auth.AuthError as e:
        print(f"Not changed: {e}")
        return 1
    print(f"\nDone. Log in as '{user.username}' with the new password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
