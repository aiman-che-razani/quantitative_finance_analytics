import os
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if os.name == "nt":
    base = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Tools\MSVC")
    candidates = sorted(base.glob("*/bin/Hostx64/x64/cl.exe"))
    if not candidates:
        raise SystemExit("Install Visual Studio C++ build tools")
    compiler = candidates[-1]
    env = {**os.environ, "PATH": str(compiler.parent) + os.pathsep + os.environ["PATH"]}
    subprocess.run(
        [
            str(compiler),
            "/nologo",
            "/O2",
            "/LD",
            "/GS-",
            "rolling.cpp",
            "/link",
            "/NOENTRY",
            "/NODEFAULTLIB",
            "/OUT:rolling.dll",
        ],
        cwd=root / "native",
        env=env,
        check=True,
    )
else:
    subprocess.run(
        [
            shutil.which("c++") or "c++",
            "-O3",
            "-shared",
            "-fPIC",
            "rolling.cpp",
            "-o",
            "rolling.so",
        ],
        cwd=root / "native",
        check=True,
    )
