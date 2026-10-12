"""Runtime configuration.

Everything is driven by environment variables so the same code runs unchanged
in dev / staging / prod. Paths default to the starter kit that ships next to
this repo, so `uvicorn meridian_service.api:app` just works from a clean clone.
"""

from __future__ import annotations

import os
from datetime import date
from dataclasses import dataclass
from pathlib import Path

# Repo root is two levels up from this file: <root>/service/meridian_service/config.py
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The exports cover 2026-W32..2026-W39 (2026-08-03 .. 2026-09-27 inclusive).
#: "last 7 days", "last month", etc. are computed relative to the day *after*
#: the last day of data, so the newest full day is always included. Documented
#: in the README.
DATA_WINDOW_END_EXCLUSIVE = date(2026, 9, 28)


@dataclass(frozen=True)
class Settings:
    environment: str
    data_dir: Path
    environments_dir: Path
    capability_store_path: Path
    anchor_end_exclusive: date

    @property
    def claude_dir(self) -> Path:
        return self.data_dir / "claude"

    @property
    def gemini_dir(self) -> Path:
        return self.data_dir / "gemini"

    @property
    def directory_dir(self) -> Path:
        return self.data_dir / "directory"

    @property
    def env_file(self) -> Path:
        return self.environments_dir / f"{self.environment}.yaml"


def load_settings() -> Settings:
    environment = os.environ.get("MERIDIAN_ENV", "dev").strip().lower()
    data_dir = Path(
        os.environ.get("MERIDIAN_DATA_DIR", _REPO_ROOT / "starter-kit" / "data")
    ).resolve()
    environments_dir = Path(
        os.environ.get("MERIDIAN_ENVIRONMENTS_DIR", _REPO_ROOT / "starter-kit" / "environments")
    ).resolve()
    # Capability edits must survive a restart, so they live outside the read-only
    # exports. Default to a writable file under the service package's parent.
    capability_store_path = Path(
        os.environ.get(
            "MERIDIAN_CAPABILITY_STORE",
            _REPO_ROOT / "service" / f".capabilities.{environment}.sqlite3",
        )
    ).resolve()
    return Settings(
        environment=environment,
        data_dir=data_dir,
        environments_dir=environments_dir,
        capability_store_path=capability_store_path,
        anchor_end_exclusive=DATA_WINDOW_END_EXCLUSIVE,
    )
