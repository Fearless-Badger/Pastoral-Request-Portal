"""Wipe the local SQLite database and migrations, then rebuild from scratch.

Local development only. Refuses to run when IS_PROD=True, because deleting an
applied migration desyncs prod's django_migrations table from the repo.

    uv run python fresh.py
    uv run python fresh.py --yes    # skip the confirmation prompt
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
MANAGE = BASE_DIR / "src" / "manage.py"
MIGRATIONS = BASE_DIR / "src" / "lucid" / "migrations"
DB_FILES = [
    BASE_DIR / "src" / "db.sqlite3",
    BASE_DIR / "src" / "db.sqlite3-shm",
    BASE_DIR / "src" / "db.sqlite3-wal",
]


def guard_prod() -> None:
    load_dotenv(BASE_DIR / ".env")
    if os.getenv("IS_PROD", "False") == "True":
        sys.exit("Refusing to run: IS_PROD=True. This is a local-only script.")


def confirm() -> None:
    if "--yes" in sys.argv:
        return
    print("This deletes the local database and all migrations. Data is not recoverable.")
    if input("Type 'fresh' to continue: ").strip() != "fresh":
        sys.exit("Aborted.")


def wipe() -> None:
    for path in DB_FILES:
        if path.exists():
            path.unlink()
            print(f"removed {path.relative_to(BASE_DIR)}")

    for path in sorted(MIGRATIONS.glob("0*.py")):
        path.unlink()
        print(f"removed {path.relative_to(BASE_DIR)}")


def rebuild() -> None:
    for command in (["makemigrations"], ["migrate"]):
        result = subprocess.run([sys.executable, str(MANAGE), *command])
        if result.returncode != 0:
            sys.exit(result.returncode)


if __name__ == "__main__":
    guard_prod()
    confirm()
    wipe()
    rebuild()
    print("\nDone. Run 'uv run python src/manage.py createsuperuser' next.")
