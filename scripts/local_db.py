"""Manage only this repository's isolated development PostgreSQL cluster."""

import argparse
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
DATA = RUNTIME / "postgres"
BIN = Path(os.environ.get("POSTGRES_BIN", r"C:\Program Files\PostgreSQL\18\bin"))


def write_secret(path: Path, text: str) -> None:
    """Create or replace ``path`` readable by the owner only (mode ignored on Windows)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o600)  # O_CREAT's mode does not apply to a file that already existed


def run(*args):
    subprocess.run(
        [str(BIN / args[0]), *args[1:]],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # Windows-only flag
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop"])
    args = parser.parse_args()
    if args.action == "stop":
        run("pg_ctl", "-D", str(DATA), "stop", "-m", "fast")
        return
    RUNTIME.mkdir(exist_ok=True)
    if not DATA.exists():
        if (ROOT / ".env").exists():
            raise SystemExit(
                "Existing .env found; move it aside before initializing a new local cluster"
            )
        password = secrets.token_urlsafe(32)
        password_file = RUNTIME / "init-password"
        write_secret(password_file, password)
        try:
            run(
                "initdb",
                "-D",
                str(DATA),
                "-U",
                "axiom",
                "--pwfile",
                str(password_file),
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
            )
        finally:
            password_file.unlink(missing_ok=True)
        write_secret(
            ROOT / ".env",
            f"DATABASE_URL=postgresql+psycopg://axiom:{password}@127.0.0.1:55442/postgres\n"
            f"POSTGRES_PASSWORD={password}\nAPI_TOKEN={secrets.token_urlsafe(32)}\n",
        )
    run(
        "pg_ctl",
        "-D",
        str(DATA),
        "-l",
        str(RUNTIME / "postgres.log"),
        "-o",
        "-h 127.0.0.1 -p 55442",
        "start",
    )


if __name__ == "__main__":
    main()
