"""In-memory usage store and the aggregation queries the API exposes.

The dataset is small and read-only (≈2,300 facts), so we keep every fact in
memory and aggregate on demand. The query surface mirrors what the platform
owners asked for: usage & cost by platform, by group, by week, and the per-user
leaderboard behind ``top_users``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from .directory import Directory
from .models import PlatformTotals, UsageFact
from .periods import DateRange, iso_week_of

PLATFORMS = ("claude", "gemini")


@dataclass
class UserTotals:
    user_id: str
    name: str
    email: str
    group_id: str
    total_tokens: int = 0
    cost_usd: Decimal = Decimal(0)


class UsageStore:
    def __init__(self, facts: list[UsageFact], directory: Directory) -> None:
        self._facts = facts
        self._directory = directory

    @property
    def facts(self) -> list[UsageFact]:
        return self._facts

    def _in_scope(self, group_id: str, date_range: DateRange) -> list[UsageFact]:
        return [
            f
            for f in self._facts
            if f.group_id == group_id and date_range.contains(f.day)
        ]

    # ----- usage_summary -------------------------------------------------
    def summary(self, group_id: str, date_range: DateRange) -> dict:
        per_platform = {p: PlatformTotals(platform=p) for p in PLATFORMS}
        for fact in self._in_scope(group_id, date_range):
            per_platform[fact.platform].add(fact)

        platforms = [per_platform[p] for p in PLATFORMS]
        total_tokens = sum(p.total_tokens for p in platforms)
        total_cost = sum((p.cost_usd for p in platforms), Decimal(0))
        return {
            "group": group_id,
            "period": {
                "start": date_range.start.isoformat(),
                "end_exclusive": date_range.end_exclusive.isoformat(),
            },
            "platforms": [
                {
                    "platform": p.platform,
                    "requests": p.requests,
                    "input_tokens": p.input_tokens,
                    "output_tokens": p.output_tokens,
                    "total_tokens": p.total_tokens,
                    "cost_usd": _money(p.cost_usd),
                }
                for p in platforms
            ],
            "totals": {
                "total_tokens": total_tokens,
                "cost_usd": _money(total_cost),
            },
        }

    # ----- top_users -----------------------------------------------------
    def top_users(self, group_id: str, date_range: DateRange, limit: int) -> list[dict]:
        totals: dict[str, UserTotals] = {}
        for fact in self._in_scope(group_id, date_range):
            entry = totals.get(fact.user_id)
            if entry is None:
                user = self._directory.user_by_id(fact.user_id)
                entry = UserTotals(
                    user_id=fact.user_id,
                    name=user.name if user else fact.user_id,
                    email=user.email if user else "",
                    group_id=group_id,
                )
                totals[fact.user_id] = entry
            entry.total_tokens += fact.total_tokens
            entry.cost_usd += fact.cost_usd

        ranked = sorted(
            totals.values(),
            key=lambda u: (u.total_tokens, u.cost_usd),
            reverse=True,
        )[:limit]
        return [
            {
                "user_id": u.user_id,
                "name": u.name,
                "email": u.email,
                "group": u.group_id,
                "total_tokens": u.total_tokens,
                "cost_usd": _money(u.cost_usd),
            }
            for u in ranked
        ]

    # ----- weekly breakdown (admin page) --------------------------------
    def weekly_breakdown(self, group_id: str, date_range: DateRange) -> list[dict]:
        by_week: dict[str, dict[str, PlatformTotals]] = defaultdict(
            lambda: {p: PlatformTotals(platform=p) for p in PLATFORMS}
        )
        for fact in self._in_scope(group_id, date_range):
            by_week[iso_week_of(fact.day)][fact.platform].add(fact)

        rows = []
        for week in sorted(by_week):
            platforms = by_week[week]
            rows.append(
                {
                    "week": week,
                    "claude": {
                        "total_tokens": platforms["claude"].total_tokens,
                        "cost_usd": _money(platforms["claude"].cost_usd),
                    },
                    "gemini": {
                        "total_tokens": platforms["gemini"].total_tokens,
                        "cost_usd": _money(platforms["gemini"].cost_usd),
                    },
                }
            )
        return rows


def _money(amount: Decimal) -> float:
    # One rounding, at the boundary: 6 dp preserves sub-cent Gemini SKUs.
    return float(round(amount, 6))
