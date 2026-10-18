"""Package source code only -> /workspace/wagmi_tracker-code.zip (no cache, screenshots, git, venv, logs)."""
import os, zipfile
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(ROOT), "wagmi_tracker-code.zip")
SKIP_DIRS = {"cache", "screenshots", ".git", "__pycache__", "venv", ".venv", "node_modules"}
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            if f.endswith((".log", ".pyc")): continue
            p = os.path.join(d, f); z.write(p, os.path.join("wagmi_tracker", os.path.relpath(p, ROOT)))
print(OUT)
