"""Stop only verified Axiom listeners on its two development ports."""

from pathlib import Path

import psutil

root = Path(__file__).resolve().parents[1]
for connection in psutil.net_connections(kind="tcp"):
    if connection.status != "LISTEN" or connection.laddr.port not in [8820, 8821]:
        continue
    process = psutil.Process(connection.pid)
    command = " ".join(process.cmdline())
    expected = root if connection.laddr.port == 8820 else root / "apps/dashboard"
    if Path(process.cwd()).resolve() != expected:
        raise RuntimeError("Port belongs to another workspace")
    if (connection.laddr.port == 8820 and "axiom.api:create_app" not in command) or (
        connection.laddr.port == 8821 and "next" not in command
    ):
        raise RuntimeError("Port is not an Axiom server")
    children = process.children(recursive=True)
    for child in children:
        child.terminate()
    process.terminate()
    psutil.wait_procs(children + [process], timeout=5)
print("Stopped verified Axiom servers")
