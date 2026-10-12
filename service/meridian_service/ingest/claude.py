"""Map the Claude Enterprise Analytics export into canonical ``UsageFact`` rows.

Two files, same buckets:

  * ``user_usage_report.json`` — tokens & requests, one row per
    user x day x product x model (x context_window x speed x geo).
  * ``user_cost_report.json``  — cost in **cents as decimal strings**, the same
    buckets split further by ``cost_type`` (``tokens`` | ``web_search``).

The usage report has no cost and the cost report has no token breakdown, so we
join them. The join key below is unique in both files (verified: 1,346 usage
rows ↔ 1,346 ``tokens`` cost rows, 1:1, no orphans), and the 492 ``web_search``
cost rows add onto the matching usage row.

Token model (confirmed by row arithmetic):
    total_tokens = uncached_input + cache_read_input
                 + cache_creation(5m + 1h) + output
so ``input_tokens = total_tokens - output_tokens``.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..directory import Directory
from ..models import UsageFact

# Cost strings are cents; divide by 100 for USD.
_CENTS = Decimal(100)


def _day_of(rfc3339: str) -> date:
    # "2026-08-03T00:00:00.000Z" -> date(2026, 8, 3)
    return datetime.fromisoformat(rfc3339.replace("Z", "+00:00")).date()


def _join_key(row: dict) -> tuple:
    return (
        row["actor"]["user_id"],
        row["starting_at"],
        row["product"],
        row["model"],
        row.get("context_window"),
        row.get("speed"),
        row.get("inference_geo"),
    )


def _input_tokens(row: dict) -> int:
    cc = row.get("cache_creation") or {}
    return (
        int(row.get("uncached_input_tokens", 0))
        + int(row.get("cache_read_input_tokens", 0))
        + int(cc.get("ephemeral_5m_input_tokens", 0))
        + int(cc.get("ephemeral_1h_input_tokens", 0))
    )


def load_claude_facts(claude_dir: Path, directory: Directory) -> list[UsageFact]:
    usage = json.loads((claude_dir / "user_usage_report.json").read_text("utf-8"))["data"]
    cost = json.loads((claude_dir / "user_cost_report.json").read_text("utf-8"))["data"]

    # Index cost by (join_key, cost_type) -> USD. Sum defensively in case a
    # future export ever splits a bucket further than we expect.
    cost_by_key: dict[tuple, Decimal] = {}
    for row in cost:
        key = (_join_key(row), row["cost_type"])
        cost_by_key[key] = cost_by_key.get(key, Decimal(0)) + Decimal(row["amount"]) / _CENTS

    facts: list[UsageFact] = []
    for row in usage:
        key = _join_key(row)
        group = directory.group_for_rbac(row["rbac_group_id"])
        user = directory.user_by_id(row["actor"]["user_id"])
        if group is None or user is None:
            # Unattributable row — surfaced by tests/ingest report, never dropped silently.
            raise ValueError(
                f"Claude row not attributable: user={row['actor']['user_id']} "
                f"rbac={row['rbac_group_id']}"
            )

        token_cost = cost_by_key.get((key, "tokens"), Decimal(0))
        web_cost = cost_by_key.get((key, "web_search"), Decimal(0))
        total = int(row["total_tokens"])
        output = int(row["output_tokens"])

        facts.append(
            UsageFact(
                platform="claude",
                day=_day_of(row["starting_at"]),
                user_id=user.user_id,
                group_id=group.group_id,
                surface=row["product"],
                model=row["model"],
                input_tokens=total - output,
                output_tokens=output,
                total_tokens=total,
                cost_usd=token_cost + web_cost,
                requests=int(row.get("requests", 0)),
                web_search_requests=int((row.get("server_tool_use") or {}).get("web_search_requests", 0)),
            )
        )
    return facts
