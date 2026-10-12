"""The permission engine — one place, enforced in code.

Every read and every write funnels through ``authorize_read`` /
``authorize_write``. They answer three questions in order:

  1. Scope — does the caller's *role* hold the scope this action needs?
     (``usage:read`` / ``capabilities:write``, per the environment manifest.)
  2. Visibility — may the caller see *this group*? Platform admins see every
     group; everyone else is bounded by the environment's ``group_visibility``
     for reads, and always to their own group for writes.
  3. (writes) nothing further here; capability gating for the connector lives in
     the connector, using the same manifest.

A failed check raises ``PermissionDenied`` carrying the exact ``Denial`` shape
from the tool contract, so the API and the MCP server emit identical denials.
"""

from __future__ import annotations

from dataclasses import dataclass

from .directory import Directory, User
from .envspec import EnvManifest

USAGE_READ = "usage:read"
CAPABILITIES_WRITE = "capabilities:write"


@dataclass(frozen=True)
class Denial:
    reason: str
    required_scope: str | None = None

    def to_dict(self) -> dict:
        body = {"error": "permission_denied", "reason": self.reason}
        if self.required_scope is not None:
            body["required_scope"] = self.required_scope
        return body


class PermissionDenied(Exception):
    def __init__(self, denial: Denial) -> None:
        super().__init__(denial.reason)
        self.denial = denial


class Authorizer:
    def __init__(self, directory: Directory, manifest: EnvManifest) -> None:
        self._directory = directory
        self._manifest = manifest

    # ----- helpers -------------------------------------------------------
    def _is_admin(self, user: User) -> bool:
        return user.role == "platform_admin"

    def visible_groups(self, user: User) -> set[str]:
        """Groups this caller may *read*, given their role and the environment."""
        if self._is_admin(user):
            return set(self._directory.group_ids)
        if self._manifest.group_visibility == "all":
            return set(self._directory.group_ids)
        return set(user.group_ids)

    def default_group(self, user: User) -> str:
        return user.group_ids[0]

    def resolve_group(self, user: User, requested: str | None) -> str:
        return requested if requested else self.default_group(user)

    # ----- reads ---------------------------------------------------------
    def authorize_read(self, user: User, group_id: str) -> None:
        if user.role not in self._manifest.usage_read_roles:
            raise PermissionDenied(
                Denial(
                    reason=f"Role '{user.role}' does not hold {USAGE_READ} in "
                    f"the {self._manifest.environment} environment.",
                    required_scope=USAGE_READ,
                )
            )
        if group_id not in self.visible_groups(user):
            raise PermissionDenied(
                Denial(
                    reason=f"Not permitted to view group '{group_id}'. "
                    f"You may view: {sorted(self.visible_groups(user))}.",
                )
            )

    # ----- writes --------------------------------------------------------
    def authorize_write(self, user: User, group_id: str) -> None:
        if user.role not in self._manifest.capabilities_write_roles:
            raise PermissionDenied(
                Denial(
                    reason=f"Role '{user.role}' may not change capability controls "
                    f"in the {self._manifest.environment} environment.",
                    required_scope=CAPABILITIES_WRITE,
                )
            )
        # Writes are always own-group for non-admins, regardless of read
        # visibility: a team lead must never toggle another group's controls.
        if not self._is_admin(user) and group_id not in set(user.group_ids):
            raise PermissionDenied(
                Denial(
                    reason=f"Not permitted to change controls for group '{group_id}'. "
                    f"You may change: {sorted(user.group_ids)}.",
                )
            )
