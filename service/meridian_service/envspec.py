"""Parse an ``environments/<env>.yaml`` file into a structured manifest.

The YAML files are "intent, not a schema" per the brief, so this module is the
one place that interprets them. Both the permission engine and the capability
defaults read the result, and the provisioning step renders from the very same
shape — nothing downstream re-parses raw YAML.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CAPABILITIES = ("usage-connector", "web-search", "code-execution")


@dataclass(frozen=True)
class CapabilityDefault:
    """A capability's default enablement, possibly scoped to specific groups."""

    enabled: bool | None  # non-None => same for every group
    enabled_for: frozenset[str] | None  # non-None => enabled only for these groups

    def resolve(self, group_id: str) -> bool:
        if self.enabled_for is not None:
            return group_id in self.enabled_for
        return bool(self.enabled)


@dataclass(frozen=True)
class EnvManifest:
    environment: str
    server_name: str
    usage_read_roles: frozenset[str]
    group_visibility: str  # "all" | "own_group"
    capabilities_write_roles: frozenset[str]
    capability_defaults: dict[str, CapabilityDefault]

    def default_for(self, capability: str, group_id: str) -> bool:
        default = self.capability_defaults.get(capability)
        return default.resolve(group_id) if default else False


def _parse_capability_default(value) -> CapabilityDefault:
    if isinstance(value, str):
        return CapabilityDefault(enabled=(value.strip().lower() == "enabled"), enabled_for=None)
    if isinstance(value, dict) and "enabled_for" in value:
        return CapabilityDefault(enabled=None, enabled_for=frozenset(value["enabled_for"]))
    raise ValueError(f"Unrecognised capability default: {value!r}")


def load_env_manifest(env_file: Path) -> EnvManifest:
    raw = yaml.safe_load(env_file.read_text("utf-8"))
    scopes = raw["scopes"]
    usage_read = scopes["usage:read"]
    cap_write = scopes["capabilities:write"]
    defaults = {
        cap: _parse_capability_default(val)
        for cap, val in raw["capability_defaults"].items()
    }
    return EnvManifest(
        environment=raw["environment"],
        server_name=raw["host"]["server_name"],
        usage_read_roles=frozenset(usage_read["roles"]),
        group_visibility=usage_read["group_visibility"],
        capabilities_write_roles=frozenset(cap_write["roles"]),
        capability_defaults=defaults,
    )
