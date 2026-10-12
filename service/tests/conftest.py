"""Shared fixtures: build a service context per environment with a temp store."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_service.config import DATA_WINDOW_END_EXCLUSIVE, Settings
from meridian_service.context import AppContext, build_context

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "starter-kit" / "data"
_ENV_DIR = _REPO_ROOT / "starter-kit" / "environments"


def make_context(tmp_path: Path, environment: str) -> AppContext:
    settings = Settings(
        environment=environment,
        data_dir=_DATA_DIR,
        environments_dir=_ENV_DIR,
        capability_store_path=tmp_path / f"caps.{environment}.sqlite3",
        anchor_end_exclusive=DATA_WINDOW_END_EXCLUSIVE,
    )
    return build_context(settings)


@pytest.fixture
def dev_ctx(tmp_path) -> AppContext:
    return make_context(tmp_path, "dev")


@pytest.fixture
def staging_ctx(tmp_path) -> AppContext:
    return make_context(tmp_path, "staging")


@pytest.fixture
def prod_ctx(tmp_path) -> AppContext:
    return make_context(tmp_path, "prod")
