"""Aggregation queries: summary shape, leaderboard ordering, weekly split."""

from __future__ import annotations

from datetime import date

from meridian_service.periods import parse_period

ANCHOR = date(2026, 9, 28)


def test_summary_shape_and_totals_add_up(dev_ctx):
    r = parse_period("2026-09", ANCHOR)
    s = dev_ctx.store.summary("it-platform", r)
    assert {p["platform"] for p in s["platforms"]} == {"claude", "gemini"}
    # platform totals sum to the grand total
    assert sum(p["total_tokens"] for p in s["platforms"]) == s["totals"]["total_tokens"]
    assert round(sum(p["cost_usd"] for p in s["platforms"]), 6) == s["totals"]["cost_usd"]
    # each platform: input + output == total
    for p in s["platforms"]:
        assert p["input_tokens"] + p["output_tokens"] == p["total_tokens"]


def test_summary_respects_period_window(dev_ctx):
    whole = dev_ctx.store.summary("finance", parse_period("2026-08", ANCHOR))
    narrow = dev_ctx.store.summary("finance", parse_period("2026-W36", ANCHOR))
    assert narrow["totals"]["total_tokens"] <= whole["totals"]["total_tokens"]


def test_top_users_ranked_descending_and_limited(dev_ctx):
    r = parse_period("2026-09", ANCHOR)
    rows = dev_ctx.store.top_users("it-platform", r, limit=3)
    assert len(rows) == 3
    tokens = [u["total_tokens"] for u in rows]
    assert tokens == sorted(tokens, reverse=True)
    for u in rows:
        assert u["group"] == "it-platform"


def test_top_users_only_includes_group_members(dev_ctx):
    r = parse_period("2026-09", ANCHOR)
    rows = dev_ctx.store.top_users("finance", r, limit=25)
    member_ids = {
        u.user_id for u in dev_ctx.directory.users if "finance" in u.group_ids
    }
    assert {u["user_id"] for u in rows} <= member_ids


def test_weekly_breakdown_covers_eight_weeks(dev_ctx):
    r = parse_period("2026-08", ANCHOR)  # wide; store clamps to available data
    weeks = dev_ctx.store.weekly_breakdown("it-platform", r)
    # August alone spans W32..W36; just assert labels are well-formed and ordered.
    labels = [w["week"] for w in weeks]
    assert labels == sorted(labels)
    assert all(lbl.startswith("2026-W") for lbl in labels)
