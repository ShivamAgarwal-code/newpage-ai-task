"""End-to-end API tests through FastAPI's TestClient.

Covers identity resolution, the contract denial shape over HTTP, period
validation, and that a capability write persists and is attributed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from meridian_service.api import create_app

PRIYA_LEAD = "priya.nair@meridianls.example"
DANIEL_MEMBER = "daniel.okafor@meridianls.example"
CHLOE_ADMIN = "chloe.dubois@meridianls.example"


def client(ctx) -> TestClient:
    return TestClient(create_app(ctx))


def test_missing_identity_is_401(dev_ctx):
    c = client(dev_ctx)
    assert c.get("/api/usage/summary", params={"period": "2026-09"}).status_code == 401


def test_unknown_caller_is_401(dev_ctx):
    c = client(dev_ctx)
    r = c.get("/api/usage/summary", params={"period": "2026-09"}, headers={"X-Actor": "nobody@x"})
    assert r.status_code == 401


def test_me_reports_scopes(prod_ctx):
    c = client(prod_ctx)
    r = c.get("/api/me", headers={"X-Actor": PRIYA_LEAD})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "team_lead"
    assert body["scopes"]["usage:read"] is True
    assert body["scopes"]["capabilities:write"] is False  # prod: admins only
    assert body["visible_groups"] == ["clinical-operations"]


def test_summary_happy_path_defaults_to_own_group(prod_ctx):
    c = client(prod_ctx)
    r = c.get("/api/usage/summary", params={"period": "2026-09"}, headers={"X-Actor": PRIYA_LEAD})
    assert r.status_code == 200
    assert r.json()["group"] == "clinical-operations"


def test_cross_group_read_denied_with_contract_shape(prod_ctx):
    c = client(prod_ctx)
    r = c.get(
        "/api/usage/summary",
        params={"period": "2026-09", "group": "finance"},
        headers={"X-Actor": PRIYA_LEAD},
    )
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "permission_denied"
    assert "reason" in body
    # and crucially: no usage data leaked
    assert "platforms" not in body and "totals" not in body


def test_member_denied_read_in_prod_names_required_scope(prod_ctx):
    c = client(prod_ctx)
    r = c.get("/api/usage/summary", params={"period": "2026-09"}, headers={"X-Actor": DANIEL_MEMBER})
    assert r.status_code == 403
    assert r.json()["required_scope"] == "usage:read"


def test_invalid_period_is_400(dev_ctx):
    c = client(dev_ctx)
    r = c.get("/api/usage/summary", params={"period": "someday"}, headers={"X-Actor": CHLOE_ADMIN})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_period"


def test_set_capability_persists_and_attributes(prod_ctx):
    c = client(prod_ctx)
    # admin disables code-execution for finance
    r = c.post(
        "/api/capabilities",
        json={"group": "finance", "capability": "code-execution", "enabled": True},
        headers={"X-Actor": CHLOE_ADMIN},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["updated_by"] == CHLOE_ADMIN
    assert body["updated_at"] is not None

    # reflected on read
    r2 = c.get("/api/capabilities", params={"group": "finance"}, headers={"X-Actor": CHLOE_ADMIN})
    states = {row["capability"]: row for row in r2.json()}
    assert states["code-execution"]["enabled"] is True
    assert states["code-execution"]["updated_by"] == CHLOE_ADMIN


def test_lead_cannot_write_in_prod(prod_ctx):
    c = client(prod_ctx)
    r = c.post(
        "/api/capabilities",
        json={"group": "clinical-operations", "capability": "web-search", "enabled": False},
        headers={"X-Actor": PRIYA_LEAD},
    )
    assert r.status_code == 403
    assert r.json()["required_scope"] == "capabilities:write"


def test_prod_capability_defaults_scoped(prod_ctx):
    """usage-connector is enabled only for it-platform & clinical-operations in prod."""
    c = client(prod_ctx)
    enabled = {}
    for group in ("it-platform", "clinical-operations", "finance", "hr"):
        rows = c.get("/api/capabilities", params={"group": group}, headers={"X-Actor": CHLOE_ADMIN}).json()
        enabled[group] = {r["capability"]: r["enabled"] for r in rows}["usage-connector"]
    assert enabled == {
        "it-platform": True,
        "clinical-operations": True,
        "finance": False,
        "hr": False,
    }
