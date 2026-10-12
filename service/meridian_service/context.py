"""Wire the pieces into one context object.

Built once at startup (and once per test), this holds the directory, the parsed
environment manifest, the ingested usage store and the capability store, plus a
ready-to-use authorizer. Everything the API and tests need hangs off here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .capabilities import CapabilityStore
from .config import Settings, load_settings
from .directory import Directory
from .envspec import EnvManifest, load_env_manifest
from .ingest import load_all_facts
from .permissions import Authorizer
from .store import UsageStore


@dataclass
class AppContext:
    settings: Settings
    directory: Directory
    manifest: EnvManifest
    store: UsageStore
    capabilities: CapabilityStore
    authorizer: Authorizer


def build_context(settings: Settings | None = None) -> AppContext:
    settings = settings or load_settings()
    directory = Directory.load(settings.directory_dir)
    manifest = load_env_manifest(settings.env_file)
    facts = load_all_facts(settings, directory)
    store = UsageStore(facts, directory)
    capabilities = CapabilityStore(
        settings.capability_store_path, manifest, directory.group_ids
    )
    authorizer = Authorizer(directory, manifest)
    return AppContext(
        settings=settings,
        directory=directory,
        manifest=manifest,
        store=store,
        capabilities=capabilities,
        authorizer=authorizer,
    )
