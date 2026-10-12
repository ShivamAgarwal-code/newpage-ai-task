"""Map the Google Cloud (Vertex AI) billing export into canonical ``UsageFact``.

Each JSONL line is one project x day x SKU. A SKU is either input *or* output
tokens for a model, e.g. ``"Gemini 2.5 Flash Text Output Tokens - Predictions"``.
We fold the input and output SKU rows for the same
(owner, day, project, model) back into one fact.

Attribution:
  * group  <- project.id          (groups.json: gcp_project_id)
  * user   <- owner label (email) (directory: email)

Units & money:
  * usage.amount is a token count (usage.unit == "count").
  * cost is already USD (credits empty in this export).
  * timestamps are BigQuery "YYYY-MM-DD HH:MM:SS UTC" strings.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..directory import Directory
from ..models import UsageFact


def _day_of(bq_timestamp: str) -> date:
    # "2026-08-05 00:00:00 UTC" -> date(2026, 8, 5)
    return datetime.strptime(bq_timestamp.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").date()


def _labels(row: dict) -> dict[str, str]:
    return {item["key"]: item["value"] for item in row.get("labels", [])}


def _is_input_sku(sku_description: str) -> bool:
    # "... Text Input Tokens - Predictions" vs "... Text Output Tokens ...".
    return "Input" in sku_description


class _Accumulator:
    __slots__ = ("input_tokens", "output_tokens", "cost_usd")

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = Decimal(0)


def load_gemini_facts(gemini_file: Path, directory: Directory) -> list[UsageFact]:
    # Fold input/output SKU rows together per logical fact key.
    acc: dict[tuple, _Accumulator] = {}
    meta: dict[tuple, tuple[str, str]] = {}  # key -> (user_id, group_id)

    with gemini_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            labels = _labels(row)
            owner_email = labels.get("owner")
            model = labels.get("model", "")
            project_id = row["project"]["id"]
            day = _day_of(row["usage_start_time"])

            group = directory.group_for_project(project_id)
            user = directory.user_by_email(owner_email) if owner_email else None
            if group is None or user is None:
                raise ValueError(
                    f"Gemini row not attributable: owner={owner_email} project={project_id}"
                )

            key = (user.user_id, day, group.group_id, model)
            bucket = acc.setdefault(key, _Accumulator())
            meta.setdefault(key, (user.user_id, group.group_id))

            tokens = int(row["usage"]["amount"])
            if _is_input_sku(row["sku"]["description"]):
                bucket.input_tokens += tokens
            else:
                bucket.output_tokens += tokens
            bucket.cost_usd += Decimal(str(row["cost"]))

    facts: list[UsageFact] = []
    for key, bucket in acc.items():
        user_id, day, group_id, model = key
        facts.append(
            UsageFact(
                platform="gemini",
                day=day,
                user_id=user_id,
                group_id=group_id,
                surface="vertex",  # Gemini workloads run as Vertex AI predictions
                model=model,
                input_tokens=bucket.input_tokens,
                output_tokens=bucket.output_tokens,
                total_tokens=bucket.input_tokens + bucket.output_tokens,
                cost_usd=bucket.cost_usd,
                requests=None,  # not present in billing rows
                web_search_requests=0,
            )
        )
    return facts
