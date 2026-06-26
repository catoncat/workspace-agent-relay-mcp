from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("WORKSPACE_AGENT_RELAY_SKIP_DOTENV", "1")

ROOT = Path(__file__).resolve().parents[1]
DIST_INDEX = ROOT / "frontend" / "dist" / "index.html"


def _build_frontend() -> None:
    subprocess.run(["bash", str(ROOT / "scripts" / "build-dashboard.sh")], check=True, cwd=ROOT)


@pytest.fixture(scope="session", autouse=True)
def ensure_frontend_dist() -> None:
    if not DIST_INDEX.is_file():
        _build_frontend()
    assert DIST_INDEX.is_file(), "frontend dist was not built"
