"""Ingest both exports into the one canonical model."""

from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..directory import Directory
from ..models import UsageFact
from .claude import load_claude_facts
from .gemini import load_gemini_facts

__all__ = ["load_all_facts", "load_claude_facts", "load_gemini_facts"]


def _gemini_file(gemini_dir: Path) -> Path:
    candidates = sorted(gemini_dir.glob("gcp_billing_export_v1_*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No Gemini billing export found under {gemini_dir}")
    return candidates[0]


def load_all_facts(settings: Settings, directory: Directory) -> list[UsageFact]:
    facts = load_claude_facts(settings.claude_dir, directory)
    facts += load_gemini_facts(_gemini_file(settings.gemini_dir), directory)
    return facts
