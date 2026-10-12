"""The directory — our stand-in for the identity provider.

Loads users.json / groups.json and builds the lookup tables the rest of the
service needs to turn export rows into people and groups:

  * Claude rows carry ``actor.user_id`` and ``rbac_group_id``.
  * Gemini rows carry an ``owner`` email label and a ``project.id``.

Both resolve to the same canonical ``user_id`` / ``group_id`` here, so the
ingest layer never hard-codes an identifier mapping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class User:
    user_id: str
    email: str
    name: str
    role: str  # member | team_lead | platform_admin
    group_ids: tuple[str, ...]


@dataclass(frozen=True)
class Group:
    group_id: str
    name: str
    team_lead_user_id: str
    claude_rbac_group_id: str
    gcp_project_id: str


class Directory:
    def __init__(self, users: list[User], groups: list[Group]) -> None:
        self._users_by_id = {u.user_id: u for u in users}
        self._users_by_email = {u.email.lower(): u for u in users}
        self._groups_by_id = {g.group_id: g for g in groups}
        # Reverse indexes used during ingest attribution.
        self._group_by_rbac = {g.claude_rbac_group_id: g for g in groups}
        self._group_by_project = {g.gcp_project_id: g for g in groups}

    # ----- construction -------------------------------------------------
    @classmethod
    def load(cls, directory_dir: Path) -> "Directory":
        users_raw = json.loads((directory_dir / "users.json").read_text("utf-8"))
        groups_raw = json.loads((directory_dir / "groups.json").read_text("utf-8"))
        users = [
            User(
                user_id=u["user_id"],
                email=u["email"],
                name=u["name"],
                role=u["role"],
                group_ids=tuple(u["group_ids"]),
            )
            for u in users_raw["users"]
        ]
        groups = [
            Group(
                group_id=g["group_id"],
                name=g["name"],
                team_lead_user_id=g["team_lead_user_id"],
                claude_rbac_group_id=g["claude_rbac_group_id"],
                gcp_project_id=g["gcp_project_id"],
            )
            for g in groups_raw["groups"]
        ]
        return cls(users, groups)

    # ----- user / group lookups ----------------------------------------
    @property
    def users(self) -> list[User]:
        return list(self._users_by_id.values())

    @property
    def groups(self) -> list[Group]:
        return list(self._groups_by_id.values())

    @property
    def group_ids(self) -> list[str]:
        return list(self._groups_by_id.keys())

    def user_by_id(self, user_id: str) -> User | None:
        return self._users_by_id.get(user_id)

    def user_by_email(self, email: str) -> User | None:
        return self._users_by_email.get(email.lower())

    def group(self, group_id: str) -> Group | None:
        return self._groups_by_id.get(group_id)

    def resolve_caller(self, identity: str) -> User | None:
        """Resolve a simulated caller passed as either a user_id or an email."""
        if not identity:
            return None
        return self.user_by_id(identity) or self.user_by_email(identity)

    # ----- attribution helpers used by the ingest layer -----------------
    def group_for_rbac(self, rbac_group_id: str) -> Group | None:
        return self._group_by_rbac.get(rbac_group_id)

    def group_for_project(self, project_id: str) -> Group | None:
        return self._group_by_project.get(project_id)
