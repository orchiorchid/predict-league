"""Which build is running: the deploy platform's commit, or the local git checkout."""
import os
import subprocess
import time
from datetime import datetime, timezone

APP_VERSION = "2.1"
STARTED_AT = time.time()

# Render, Railway, Heroku and Fly all expose the deployed commit under one of these.
COMMIT_ENV_VARS = ("RENDER_GIT_COMMIT", "SOURCE_VERSION", "GIT_COMMIT", "RAILWAY_GIT_COMMIT_SHA", "FLY_IMAGE_REF")


def _from_env() -> str:
    for name in COMMIT_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value.strip()[:12]
    return ""


def _from_git() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        out = subprocess.run(["git", "-C", root, "rev-parse", "--short=12", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


COMMIT = _from_env() or _from_git() or "unknown"
BUILD = f"{APP_VERSION}+{COMMIT}"


def build_info() -> dict:
    return {
        "version": APP_VERSION,
        "commit": COMMIT,
        "build": BUILD,
        "started_at": datetime.fromtimestamp(STARTED_AT, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uptime_seconds": round(time.time() - STARTED_AT),
    }
