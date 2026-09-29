"""Start local API and dashboard with server-side credentials and hidden windows."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from axiom.settings import Settings

root = Path(__file__).resolve().parents[1]
node = shutil.which("node") or sys.exit("node not found on PATH")
runtime = root / ".runtime"
runtime.mkdir(exist_ok=True)
settings = Settings()
env = {**os.environ, "API_TOKEN": settings.api_token, "AXIOM_API_URL": "http://127.0.0.1:8820"}
commands = {
    "api": [
        str(root / ".venv/Scripts/python.exe")
        if os.name == "nt"
        else str(root / ".venv/bin/python"),
        "-m",
        "uvicorn",
        "axiom.api:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8820",
    ],
    "dashboard": [
        node,
        str(root / "apps/dashboard/node_modules/next/dist/bin/next"),
        "start",
        "--hostname",
        "127.0.0.1",
        "--port",
        "8821",
    ],
}
pids = {}
for name, command in commands.items():
    with (runtime / f"{name}.log").open("a", encoding="utf-8") as output:
        process = subprocess.Popen(
            command,
            cwd=root if name == "api" else root / "apps/dashboard",
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # Windows-only flag
        )
        pids[name] = process.pid
(runtime / "servers.json").write_text(json.dumps(pids))
print("API http://127.0.0.1:8820; dashboard http://127.0.0.1:8821", pids)
