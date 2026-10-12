"""The permission model is the part they test hardest — exercise every edge.

Roles x environments x read/write x own-group/cross-group. The matrix below is
the contract: a team lead sees only their own group outside dev; a member loses
read entirely in staging/prod; only platform_admin writes in prod; nobody but an
admin ever writes another group's controls.
"""

from __future__ import annotations

import pytest

from meridian_service.permissions import PermissionDenied

# Directory identities used throughout.
PRIYA_LEAD_CLINOPS = "priya.nair@meridianls.example"
DANIEL_MEMBER_CLINOPS = "daniel.okafor@meridianls.example"
MEI_LEAD_REGAFFAIRS = "mei.chen@meridianls.example"
CHLOE_ADMIN = "chloe.dubois@meridianls.example"  # it-platform, platform_admin


def _user(ctx, email):
    return ctx.directory.user_by_email(email)


# ---------- reads ----------------------------------------------------------
def test_dev_member_can_read_any_group(dev_ctx):
    daniel = _user(dev_ctx, DANIEL_MEMBER_CLINOPS)
    dev_ctx.authorizer.authorize_read(daniel, "finance")  # no raise: dev visibility=all


def test_staging_member_has_no_read_scope(staging_ctx):
    daniel = _user(staging_ctx, DANIEL_MEMBER_CLINOPS)
    with pytest.raises(PermissionDenied) as exc:
        staging_ctx.authorizer.authorize_read(daniel, "clinical-operations")
    assert exc.value.denial.required_scope == "usage:read"


def test_prod_lead_reads_own_group_only(prod_ctx):
    priya = _user(prod_ctx, PRIYA_LEAD_CLINOPS)
    prod_ctx.authorizer.authorize_read(priya, "clinical-operations")  # ok
    with pytest.raises(PermissionDenied) as exc:
        prod_ctx.authorizer.authorize_read(priya, "finance")  # cross-group
    assert exc.value.denial.required_scope is None  # a visibility denial, not a scope denial
    assert "finance" in exc.value.denial.reason


def test_prod_admin_reads_every_group(prod_ctx):
    chloe = _user(prod_ctx, CHLOE_ADMIN)
    for g in prod_ctx.directory.group_ids:
        prod_ctx.authorizer.authorize_read(chloe, g)  # no raise


# ---------- writes ---------------------------------------------------------
def test_prod_lead_cannot_write(prod_ctx):
    priya = _user(prod_ctx, PRIYA_LEAD_CLINOPS)
    with pytest.raises(PermissionDenied) as exc:
        prod_ctx.authorizer.authorize_write(priya, "clinical-operations")
    assert exc.value.denial.required_scope == "capabilities:write"


def test_prod_admin_can_write_any_group(prod_ctx):
    chloe = _user(prod_ctx, CHLOE_ADMIN)
    prod_ctx.authorizer.authorize_write(chloe, "finance")  # no raise


def test_staging_lead_writes_own_group_but_not_others(staging_ctx):
    priya = _user(staging_ctx, PRIYA_LEAD_CLINOPS)
    staging_ctx.authorizer.authorize_write(priya, "clinical-operations")  # ok
    with pytest.raises(PermissionDenied) as exc:
        staging_ctx.authorizer.authorize_write(priya, "regulatory-affairs")
    assert "regulatory-affairs" in exc.value.denial.reason


def test_dev_lead_still_cannot_write_other_group(dev_ctx):
    """Even where read visibility is 'all', writes stay own-group for non-admins."""
    mei = _user(dev_ctx, MEI_LEAD_REGAFFAIRS)
    dev_ctx.authorizer.authorize_read(mei, "finance")  # reads: fine in dev
    with pytest.raises(PermissionDenied):
        dev_ctx.authorizer.authorize_write(mei, "finance")  # writes: never


# ---------- visible_groups surface ----------------------------------------
def test_visible_groups_admin_vs_lead(prod_ctx):
    chloe = _user(prod_ctx, CHLOE_ADMIN)
    priya = _user(prod_ctx, PRIYA_LEAD_CLINOPS)
    assert prod_ctx.authorizer.visible_groups(chloe) == set(prod_ctx.directory.group_ids)
    assert prod_ctx.authorizer.visible_groups(priya) == {"clinical-operations"}
