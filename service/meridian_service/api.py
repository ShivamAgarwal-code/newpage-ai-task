"""FastAPI application: the scoped usage & admin API, plus the admin page.

Identity is simulated: the caller is a directory user passed in the ``X-Actor``
header (or ``?actor=`` for the browser page), as an email or user_id. Their role
and groups come from the directory; the environment manifest decides what that
role may see and change. Every denial is the contract's ``Denial`` shape with a
403 status.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .context import AppContext, build_context
from .directory import User
from .periods import InvalidPeriod, parse_period
from .permissions import CAPABILITIES_WRITE, PermissionDenied

_STATIC_DIR = Path(__file__).resolve().parent / "static"


class SetCapabilityBody(BaseModel):
    group: str
    capability: str
    enabled: bool


def create_app(context: AppContext | None = None) -> FastAPI:
    ctx = context or build_context()
    app = FastAPI(title="Meridian Usage & Admin Service", version="0.1.0")
    app.state.ctx = ctx

    # ----- identity dependency ------------------------------------------
    def get_caller(
        request: Request,
        x_actor: str | None = Header(default=None, alias="X-Actor"),
        actor: str | None = Query(default=None),
    ) -> User:
        identity = x_actor or actor
        if not identity:
            raise HTTPException(
                status_code=401,
                detail="Missing caller identity. Pass X-Actor (email or user_id).",
            )
        user = request.app.state.ctx.directory.resolve_caller(identity)
        if user is None:
            raise HTTPException(status_code=401, detail=f"Unknown caller: {identity!r}")
        return user

    def get_ctx(request: Request) -> AppContext:
        return request.app.state.ctx

    # ----- identity / directory -----------------------------------------
    @app.get("/api/health")
    def health(ctx: AppContext = Depends(get_ctx)) -> dict:
        return {
            "status": "ok",
            "environment": ctx.manifest.environment,
            "facts": len(ctx.store.facts),
        }

    @app.get("/api/me")
    def me(caller: User = Depends(get_caller), ctx: AppContext = Depends(get_ctx)) -> dict:
        return {
            "user_id": caller.user_id,
            "name": caller.name,
            "email": caller.email,
            "role": caller.role,
            "group_ids": list(caller.group_ids),
            "environment": ctx.manifest.environment,
            "scopes": {
                "usage:read": caller.role in ctx.manifest.usage_read_roles,
                "capabilities:write": caller.role in ctx.manifest.capabilities_write_roles,
            },
            "visible_groups": sorted(ctx.authorizer.visible_groups(caller)),
        }

    @app.get("/api/directory")
    def directory(ctx: AppContext = Depends(get_ctx)) -> dict:
        """The seat list and groups — powers the simulated user switcher."""
        return {
            "users": [
                {
                    "user_id": u.user_id,
                    "name": u.name,
                    "email": u.email,
                    "role": u.role,
                    "group_ids": list(u.group_ids),
                }
                for u in ctx.directory.users
            ],
            "groups": [
                {"group_id": g.group_id, "name": g.name} for g in ctx.directory.groups
            ],
        }

    # ----- usage ---------------------------------------------------------
    @app.get("/api/usage/summary")
    def usage_summary(
        period: str = Query(...),
        group: str | None = Query(default=None),
        caller: User = Depends(get_caller),
        ctx: AppContext = Depends(get_ctx),
    ):
        group_id = ctx.authorizer.resolve_group(caller, group)
        _require_known_group(ctx, group_id)
        ctx.authorizer.authorize_read(caller, group_id)
        date_range = _parse_period(ctx, period)
        return ctx.store.summary(group_id, date_range)

    @app.get("/api/usage/top-users")
    def top_users(
        period: str = Query(...),
        group: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=25),
        caller: User = Depends(get_caller),
        ctx: AppContext = Depends(get_ctx),
    ):
        group_id = ctx.authorizer.resolve_group(caller, group)
        _require_known_group(ctx, group_id)
        ctx.authorizer.authorize_read(caller, group_id)
        date_range = _parse_period(ctx, period)
        return ctx.store.top_users(group_id, date_range, limit)

    @app.get("/api/usage/weekly")
    def weekly(
        period: str = Query(default="2026-08"),
        group: str | None = Query(default=None),
        caller: User = Depends(get_caller),
        ctx: AppContext = Depends(get_ctx),
    ):
        group_id = ctx.authorizer.resolve_group(caller, group)
        _require_known_group(ctx, group_id)
        ctx.authorizer.authorize_read(caller, group_id)
        # The admin chart wants the full window; accept any period but default wide.
        date_range = _parse_period(ctx, period)
        return {"group": group_id, "weeks": ctx.store.weekly_breakdown(group_id, date_range)}

    # ----- capabilities --------------------------------------------------
    @app.get("/api/capabilities")
    def capability_status(
        group: str | None = Query(default=None),
        caller: User = Depends(get_caller),
        ctx: AppContext = Depends(get_ctx),
    ):
        group_id = ctx.authorizer.resolve_group(caller, group)
        _require_known_group(ctx, group_id)
        ctx.authorizer.authorize_read(caller, group_id)
        return [
            {
                "group": s.group,
                "capability": s.capability,
                "enabled": s.enabled,
                "updated_at": s.updated_at,
                "updated_by": s.updated_by,
            }
            for s in ctx.capabilities.list_for_group(group_id)
        ]

    @app.post("/api/capabilities")
    def set_capability(
        body: SetCapabilityBody,
        caller: User = Depends(get_caller),
        ctx: AppContext = Depends(get_ctx),
    ):
        _require_known_group(ctx, body.group)
        if body.capability not in ("usage-connector", "web-search", "code-execution"):
            raise HTTPException(status_code=400, detail=f"Unknown capability: {body.capability}")
        ctx.authorizer.authorize_write(caller, body.group)
        state = ctx.capabilities.set(body.group, body.capability, body.enabled, caller.email)
        return {
            "group": state.group,
            "capability": state.capability,
            "enabled": state.enabled,
            "updated_at": state.updated_at,
            "updated_by": state.updated_by,
        }

    # ----- permission denials -> contract Denial shape ------------------
    @app.exception_handler(PermissionDenied)
    async def _denied(_request: Request, exc: PermissionDenied):
        return JSONResponse(status_code=403, content=exc.denial.to_dict())

    @app.exception_handler(InvalidPeriod)
    async def _bad_period(_request: Request, exc: InvalidPeriod):
        return JSONResponse(status_code=400, content={"error": "invalid_period", "reason": str(exc)})

    # ----- admin page ----------------------------------------------------
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

        @app.get("/")
        def admin_page():
            return FileResponse(str(_STATIC_DIR / "admin.html"))

    return app


def _require_known_group(ctx: AppContext, group_id: str) -> None:
    if ctx.directory.group(group_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown group: {group_id}")


def _parse_period(ctx: AppContext, period: str):
    return parse_period(period, ctx.settings.anchor_end_exclusive)


# Module-level app for `uvicorn meridian_service.api:app`.
app = create_app()


def main() -> None:  # console entry point
    import uvicorn

    uvicorn.run("meridian_service.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
