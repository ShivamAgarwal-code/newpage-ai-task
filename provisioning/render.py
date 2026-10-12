#!/usr/bin/env python3
"""Render the permissions manifest and host registration config per environment.

One command, three environments, no hand-editing:

    python provisioning/render.py            # render every env + validate
    python provisioning/render.py --check    # validate + fail on drift (CI)
    python provisioning/render.py --env prod # just one

For each of dev / staging / prod this renders, under ``provisioning/out/<env>/``:

  * ``permissions.json``          — the resolved manifest the connector enforces
  * ``claude_desktop_config.json``— Claude Desktop / custom-connector registration
  * ``gemini-extension.json``     — Gemini CLI extension registration

Output is deterministic (no timestamps, sorted keys, ``${MERIDIAN_REPO}``
placeholder for paths) so ``--check`` can detect any divergence between the
committed files and a fresh render — that is how CI proves nothing was
hand-edited.

The YAML is interpreted by the *same* code the service uses
(``meridian_service.envspec``), so there is exactly one reading of each
environment file across the whole system.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reuse the service's single interpretation of the environment YAML + directory.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "service"))

from meridian_service.directory import Directory  # noqa: E402
from meridian_service.envspec import CAPABILITIES, load_env_manifest  # noqa: E402

ENVIRONMENTS = ("dev", "staging", "prod")
OUT_DIR = _REPO_ROOT / "provisioning" / "out"
ENV_DIR = _REPO_ROOT / "starter-kit" / "environments"
DIRECTORY_DIR = _REPO_ROOT / "starter-kit" / "data" / "directory"

# The directory user the server "starts as" by default in each environment.
# Chosen to exercise that environment's grants; override with MERIDIAN_ACTOR.
DEFAULT_ACTOR = {
    "dev": "daniel.okafor@meridianls.example",   # member — dev lets members read
    "staging": "priya.nair@meridianls.example",  # team lead — own-group visibility
    "prod": "chloe.dubois@meridianls.example",   # platform admin — all groups + writes
}

REPO = "${MERIDIAN_REPO}"  # install step substitutes the absolute repo path


def render_permissions(environment: str) -> dict:
    manifest = load_env_manifest(ENV_DIR / f"{environment}.yaml")
    directory = Directory.load(DIRECTORY_DIR)
    groups = sorted(directory.group_ids)
    return {
        "environment": manifest.environment,
        "server_name": manifest.server_name,
        "generated_by": "provisioning/render.py",
        "source": f"starter-kit/environments/{environment}.yaml",
        "scopes": {
            "usage:read": {
                "roles": sorted(manifest.usage_read_roles),
                "group_visibility": manifest.group_visibility,
            },
            "capabilities:write": {
                "roles": sorted(manifest.capabilities_write_roles),
            },
        },
        "capabilities": {
            cap: {
                "default_by_group": {g: manifest.default_for(cap, g) for g in groups}
            }
            for cap in CAPABILITIES
        },
    }


def _server_env(environment: str) -> dict:
    return {
        "MERIDIAN_ENV": environment,
        "MERIDIAN_ACTOR": DEFAULT_ACTOR[environment],
        "MERIDIAN_SERVICE_URL": "http://127.0.0.1:8000",
        "MERIDIAN_MANIFEST": f"{REPO}/provisioning/out/{environment}/permissions.json",
        "MERIDIAN_DIRECTORY": f"{REPO}/starter-kit/data/directory",
    }


def render_claude_desktop(environment: str, server_name: str) -> dict:
    """Claude Desktop / custom local connector registration (mcpServers entry)."""
    return {
        "mcpServers": {
            server_name: {
                "command": "node",
                "args": [f"{REPO}/connector/dist/index.js"],
                "env": _server_env(environment),
            }
        }
    }


def render_gemini_extension(environment: str, server_name: str) -> dict:
    """Gemini CLI extension manifest (gemini-extension.json)."""
    return {
        "name": server_name,
        "version": "0.1.0",
        "description": "Meridian AI usage & capability controls, scoped per caller.",
        "contextFileName": "GEMINI.md",
        "mcpServers": {
            server_name: {
                "command": "node",
                "args": [f"{REPO}/connector/dist/index.js"],
                "cwd": f"{REPO}/connector",
                "env": _server_env(environment),
            }
        },
    }


def render_env(environment: str) -> dict[str, dict]:
    permissions = render_permissions(environment)
    server_name = permissions["server_name"]
    return {
        "permissions.json": permissions,
        "claude_desktop_config.json": render_claude_desktop(environment, server_name),
        "gemini-extension.json": render_gemini_extension(environment, server_name),
    }


def _dumps(obj: dict) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------
# Validation — structural + semantic, run on every render and in --check.
# --------------------------------------------------------------------------
VALID_ROLES = {"member", "team_lead", "platform_admin"}
VALID_VISIBILITY = {"all", "own_group"}


def validate(environment: str, files: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    perms = files["permissions.json"]

    def err(msg: str) -> None:
        errors.append(f"[{environment}] {msg}")

    # scopes
    read = perms["scopes"]["usage:read"]
    write = perms["scopes"]["capabilities:write"]
    if not read["roles"]:
        err("usage:read has no roles")
    if set(read["roles"]) - VALID_ROLES:
        err(f"usage:read has unknown roles: {set(read['roles']) - VALID_ROLES}")
    if read["group_visibility"] not in VALID_VISIBILITY:
        err(f"bad group_visibility: {read['group_visibility']}")
    if set(write["roles"]) - VALID_ROLES:
        err(f"capabilities:write has unknown roles: {set(write['roles']) - VALID_ROLES}")
    # platform_admin must always retain write (otherwise no one can administer)
    if "platform_admin" not in write["roles"]:
        err("platform_admin must hold capabilities:write")

    # capabilities resolve for every group
    directory = Directory.load(DIRECTORY_DIR)
    for cap in CAPABILITIES:
        if cap not in perms["capabilities"]:
            err(f"missing capability default: {cap}")
            continue
        by_group = perms["capabilities"][cap]["default_by_group"]
        missing = set(directory.group_ids) - set(by_group)
        if missing:
            err(f"capability {cap} missing groups: {sorted(missing)}")

    # host configs reference the right server_name and the connector entrypoint
    server_name = perms["server_name"]
    for host_file in ("claude_desktop_config.json", "gemini-extension.json"):
        cfg = files[host_file]
        servers = cfg.get("mcpServers", {})
        if server_name not in servers:
            err(f"{host_file} does not register server '{server_name}'")
            continue
        entry = servers[server_name]
        if entry.get("command") != "node" or not any(
            a.endswith("connector/dist/index.js") for a in entry.get("args", [])
        ):
            err(f"{host_file} does not point at the connector entrypoint")
        if entry["env"]["MERIDIAN_ENV"] != environment:
            err(f"{host_file} MERIDIAN_ENV mismatch")

    # cross-check environment intent that we must never regress
    if environment == "prod":
        if write["roles"] != ["platform_admin"]:
            err("prod must restrict capabilities:write to platform_admin only")
        uc = perms["capabilities"]["usage-connector"]["default_by_group"]
        enabled = {g for g, on in uc.items() if on}
        if enabled != {"it-platform", "clinical-operations"}:
            err(f"prod usage-connector default must be it-platform+clinical-operations, got {enabled}")
    if environment == "dev" and read["group_visibility"] != "all":
        err("dev must allow all-group visibility")

    return errors


def cmd_render(environments: list[str]) -> int:
    had_errors = False
    for environment in environments:
        files = render_env(environment)
        errors = validate(environment, files)
        target = OUT_DIR / environment
        target.mkdir(parents=True, exist_ok=True)
        for name, obj in files.items():
            (target / name).write_text(_dumps(obj), encoding="utf-8")
        status = "OK" if not errors else "INVALID"
        print(f"rendered {environment:8s} -> {target.relative_to(_REPO_ROOT)}  [{status}]")
        for e in errors:
            print(f"   ! {e}")
        had_errors = had_errors or bool(errors)
    return 1 if had_errors else 0


def cmd_check(environments: list[str]) -> int:
    problems = False
    for environment in environments:
        files = render_env(environment)
        errors = validate(environment, files)
        for e in errors:
            print(f"   ! {e}")
            problems = True
        target = OUT_DIR / environment
        for name, obj in files.items():
            path = target / name
            fresh = _dumps(obj)
            if not path.exists():
                print(f"   ! [{environment}] missing committed file: {path.relative_to(_REPO_ROOT)}")
                problems = True
            elif path.read_text(encoding="utf-8") != fresh:
                print(f"   ! [{environment}] drift: {path.relative_to(_REPO_ROOT)} differs from a fresh render")
                problems = True
        if not problems:
            print(f"checked  {environment:8s}  [OK]")
    if problems:
        print("\nprovisioning check FAILED — re-run `python provisioning/render.py` and commit.")
        return 1
    print("\nprovisioning check OK — committed config matches a fresh render.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate + fail on drift (CI)")
    parser.add_argument("--env", choices=ENVIRONMENTS, help="limit to one environment")
    args = parser.parse_args()
    environments = [args.env] if args.env else list(ENVIRONMENTS)
    return cmd_check(environments) if args.check else cmd_render(environments)


if __name__ == "__main__":
    raise SystemExit(main())
