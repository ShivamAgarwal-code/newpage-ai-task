"""The mapping is the backend's core craft — pin it down hard.

These tests would catch a regression in: the two-export → one-model join, token
arithmetic, cents→USD and USD handling, and row→person/group attribution.
"""

from __future__ import annotations

from decimal import Decimal

from meridian_service.models import UsageFact


def _facts(ctx):
    return ctx.store.facts


def test_every_fact_attributes_to_a_known_user_and_group(dev_ctx):
    dir_ = dev_ctx.directory
    for f in _facts(dev_ctx):
        assert dir_.user_by_id(f.user_id) is not None
        assert dir_.group(f.group_id) is not None


def test_claude_token_arithmetic_holds(dev_ctx):
    claude = [f for f in _facts(dev_ctx) if f.platform == "claude"]
    assert claude, "expected Claude facts"
    for f in claude:
        assert f.input_tokens + f.output_tokens == f.total_tokens
        assert f.input_tokens >= 0 and f.output_tokens >= 0


def test_gemini_total_is_input_plus_output(dev_ctx):
    gemini = [f for f in _facts(dev_ctx) if f.platform == "gemini"]
    assert gemini
    for f in gemini:
        assert f.input_tokens + f.output_tokens == f.total_tokens
        assert f.requests is None  # billing rows carry no request count


def test_platform_cost_totals_match_raw_exports(dev_ctx):
    """Independent check: the one-model cost must equal the raw export totals."""
    claude = sum((f.cost_usd for f in _facts(dev_ctx) if f.platform == "claude"), Decimal(0))
    gemini = sum((f.cost_usd for f in _facts(dev_ctx) if f.platform == "gemini"), Decimal(0))
    # Figures verified directly from the starter-kit files.
    assert round(claude, 2) == Decimal("2830.29")
    assert round(gemini, 2) == Decimal("287.84")


def test_first_claude_row_maps_exactly(dev_ctx):
    """Spot-check the very first Claude bucket against the raw numbers."""
    # Priya Nair, 2026-08-03, chat, opus — from user_usage_report.json row 1.
    matches = [
        f
        for f in _facts(dev_ctx)
        if f.platform == "claude"
        and f.user_id == "user_E7691888F28227066DD2FB86"
        and f.day.isoformat() == "2026-08-03"
        and f.surface == "chat"
        and f.model == "claude-opus-5-5"
    ]
    assert len(matches) == 1
    f = matches[0]
    assert f.total_tokens == 57516
    assert f.output_tokens == 6966
    assert f.input_tokens == 57516 - 6966
    assert f.group_id == "clinical-operations"
    # token cost 88.900050c + web_search 1.000000c, both cents -> USD
    assert f.cost_usd == Decimal("88.900050") / 100 + Decimal("1.000000") / 100
    assert f.web_search_requests == 1


def test_gemini_folds_input_and_output_skus(dev_ctx):
    # Priya Nair, 2026-08-05, clinops, flash — row 1/2 of the JSONL.
    matches = [
        f
        for f in _facts(dev_ctx)
        if f.platform == "gemini"
        and f.user_id == "user_E7691888F28227066DD2FB86"
        and f.day.isoformat() == "2026-08-05"
        and f.model == "gemini-2.5-flash"
    ]
    assert len(matches) == 1
    f = matches[0]
    assert f.input_tokens == 358546
    assert f.output_tokens == 55301
    assert f.cost_usd == Decimal("0.107564") + Decimal("0.138253")


def test_claude_and_gemini_both_present(dev_ctx):
    platforms = {f.platform for f in _facts(dev_ctx)}
    assert platforms == {"claude", "gemini"}
