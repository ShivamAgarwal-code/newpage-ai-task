"""Per-group capability controls, persisted.

Capabilities (``usage-connector``, ``web-search``, ``code-execution``) are a
small (group x capability) grid that platform owners toggle. Edits must survive
a restart and must record who made them, so they live in SQLite rather than in
the read-only exports. On first start, any cell the store has never seen is
seeded from the environment's ``capability_defaults``; an explicit edit always
wins over the default thereafter.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .envspec import CAPABILITIES, EnvManifest


@dataclass(frozen=True)
class CapabilityState:
    group: str
    capability: str
    enabled: bool
    updated_at: str | None
    updated_by: str | None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class CapabilityStore:
    def __init__(self, db_path: Path, manifest: EnvManifest, group_ids: list[str]) -> None:
        self._manifest = manifest
        self._group_ids = list(group_ids)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI may serve requests on a threadpool.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS capabilities (
                group_id   TEXT NOT NULL,
                capability TEXT NOT NULL,
                enabled    INTEGER NOT NULL,
                updated_at TEXT,
                updated_by TEXT,
                PRIMARY KEY (group_id, capability)
            )
            """
        )
        self._conn.commit()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        """Insert default rows for any cell not already present (idempotent)."""
        for group_id in self._group_ids:
            for capability in CAPABILITIES:
                enabled = self._manifest.default_for(capability, group_id)
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO capabilities
                        (group_id, capability, enabled, updated_at, updated_by)
                    VALUES (?, ?, ?, NULL, NULL)
                    """,
                    (group_id, capability, int(enabled)),
                )
        self._conn.commit()

    def get(self, group_id: str, capability: str) -> CapabilityState:
        row = self._conn.execute(
            "SELECT enabled, updated_at, updated_by FROM capabilities "
            "WHERE group_id = ? AND capability = ?",
            (group_id, capability),
        ).fetchone()
        if row is None:
            # Not seeded (unknown group/capability): fall back to the default.
            enabled = self._manifest.default_for(capability, group_id)
            return CapabilityState(group_id, capability, enabled, None, None)
        return CapabilityState(group_id, capability, bool(row[0]), row[1], row[2])

    def is_enabled(self, group_id: str, capability: str) -> bool:
        return self.get(group_id, capability).enabled

    def list_for_group(self, group_id: str) -> list[CapabilityState]:
        return [self.get(group_id, cap) for cap in CAPABILITIES]

    def set(self, group_id: str, capability: str, enabled: bool, updated_by: str) -> CapabilityState:
        if capability not in CAPABILITIES:
            raise ValueError(f"Unknown capability: {capability!r}")
        now = _now()
        self._conn.execute(
            """
            INSERT INTO capabilities (group_id, capability, enabled, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(group_id, capability) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (group_id, capability, int(enabled), now, updated_by),
        )
        self._conn.commit()
        return CapabilityState(group_id, capability, enabled, now, updated_by)
