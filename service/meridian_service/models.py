"""The canonical usage model.

One ``UsageFact`` is the single shape both exports are mapped into: one row per
(platform, day, user, group, surface, model) with normalised token counts and a
single USD cost. Money is carried as ``Decimal`` all the way through aggregation
and only converted to ``float`` at the API boundary, so we never accumulate
floating-point error across 2,300+ rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

Platform = str  # "claude" | "gemini"


@dataclass(frozen=True)
class UsageFact:
    platform: Platform
    day: date
    user_id: str
    group_id: str
    surface: str          # Claude product (chat/claude_code/cowork) or Gemini agent
    model: str            # normalised model name
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: Decimal
    requests: int | None          # Claude reports it; Gemini billing does not
    web_search_requests: int      # Claude server-tool usage; 0 for Gemini


@dataclass
class PlatformTotals:
    platform: Platform
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    requests: int | None = None

    def add(self, fact: UsageFact) -> None:
        self.input_tokens += fact.input_tokens
        self.output_tokens += fact.output_tokens
        self.total_tokens += fact.total_tokens
        self.cost_usd += fact.cost_usd
        if fact.requests is not None:
            self.requests = (self.requests or 0) + fact.requests
