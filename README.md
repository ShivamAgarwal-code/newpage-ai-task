# Meridian Life Sciences — AI usage & admin platform

**Assignment ID: Fullstack-ClaudeGemini-UsageConnector-v1**

A usage-and-cost service over Meridian's Claude and Gemini AI assistants, with
per-group capability controls — and an MCP connector that brings the same data,
scoped to the caller, inside the assistant itself. A team lead can ask *"how much
did my team use last month?"* and see only their own team; a platform admin sees
everything and owns the controls.

- **Part A** — a Python / FastAPI service: ingest both exports into one model,
  a scoped API, a minimal admin page, persisted capability controls.
- **Part B** — a TypeScript MCP connector over Part A: four tools, enforcement in
  the server, provisioning for three environments, packaged for Claude and Gemini.

The language split is deliberate and (per the brief) falls out naturally: the
**service is Python**, the **connector is TypeScript** — the language MCP hosts
expect for a local server.

---

## Quick start

Prerequisites: Python 3.11+ and Node 20+.

```bash
# 1. Service (Part A)
cd service
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                                            # 42 tests
MERIDIAN_ENV=prod uvicorn meridian_service.api:app --port 8000
#   → admin page at http://127.0.0.1:8000/   ·   API under /api/*

# 2. Connector (Part B) — in another terminal
cd connector
npm ci && npm run build
npm test                                             # 14 tests

# 3. Provisioning — render manifests + host configs for dev/staging/prod
python provisioning/render.py                        # writes provisioning/out/**
python provisioning/render.py --check                # validate + drift check (CI gate)

# 4. See Part B end-to-end (service must be running)
cd connector
node scripts/transcript.mjs priya.nair@meridianls.example   prod   # team lead
node scripts/transcript.mjs chloe.dubois@meridianls.example prod   # platform admin
```

With `make`: `make setup` (installs both + renders), `make test` (everything),
`make serve`, `make demo`.

The admin page has a **user switcher** (top right) — pick any of the 22 directory
users and the page acts as them via the `X-Actor` header. Try Priya Nair (team
lead) then switch the group to Finance to see a denial; switch to Chloe Dubois
(admin) to see every group and toggle controls.

---

## Architecture

```
          Claude Enterprise            Google Cloud billing
          Analytics export             (Vertex AI) export
          (tokens + cost,              (JSONL, per-project,
           cents, 2 files)              USD, SKU rows)
                 │                             │
                 ▼                             ▼
        ingest/claude.py              ingest/gemini.py
          join usage+cost              fold input/output SKUs
          cents → USD                  attribute project→group
          rbac→group, user→user        owner-label→user
                 └──────────────┬──────────────┘
                                ▼
                     ┌──────────────────────┐
                     │  one canonical model │   UsageFact[]  (in-memory)
                     │  UsageFact           │   ≈2,300 rows, Decimal money
                     └──────────┬───────────┘
                                │
   directory.py ───────────────┤ (users, groups, roles)
   envspec.py  (env YAML) ──────┤
                                ▼
        ┌───────────────────────────────────────────┐
        │  PERMISSION ENGINE  (permissions.py)       │  ← one place, enforced in code
        │  authorize_read / authorize_write          │
        └───────┬───────────────────────────┬────────┘
                │                           │
                ▼                           ▼
      UsageStore (aggregation)     CapabilityStore (SQLite, persisted)
                │                           │
                └─────────────┬─────────────┘
                              ▼
                   FastAPI  (api.py)        ──────────►  Admin page (static/admin.html)
                   /api/usage/* /api/capabilities           user switcher, tables, toggles
                              ▲
                              │ HTTP  (X-Actor header)
                              │
        ┌─────────────────────┴───────────────────────┐
        │   MCP CONNECTOR  (TypeScript, Part B)        │  starts as a directory user
        │   permissions.ts  ← mirrors the engine       │  enforces BEFORE calling service
        │   tools.ts: usage_summary · top_users ·      │  honours usage-connector gate
        │             capability_status · set_capability│
        └─────────────────────┬───────────────────────┘
                              │ stdio (MCP)
                     Claude Desktop / Claude Code  ·  Gemini CLI
                              ▲
        provisioning/render.py ──► permissions.<env>.json  (manifest the connector enforces)
                               └──► claude_desktop_config.json, gemini-extension.json
```

Each concern is one module: **directory**, **ingest**, **permission engine**,
**usage store**, **capability store**. That is what makes the "real enterprise"
swaps at the end of this README small.

---

## Mapping decisions — two exports into one model

The one model is `UsageFact` (`service/meridian_service/models.py`): one row per
`(platform, day, user_id, group_id, surface, model)` with normalised
`input/output/total` tokens and a single `cost_usd` (Decimal).

### Claude (`ingest/claude.py`)
- **Two files, joined.** `user_usage_report.json` has tokens but no cost;
  `user_cost_report.json` has cost but no token breakdown. I join them on
  `(user_id, starting_at, product, model, context_window, speed, inference_geo)`.
  That key is **unique in both files** — verified: 1,346 usage rows ↔ 1,346
  `tokens` cost rows, 1:1, no orphans — and the 492 `web_search` cost rows add
  onto the matching usage row. So each fact carries token *and* full cost.
- **Cost units.** `amount` / `list_amount` are decimal strings **in cents**
  (`"88.900050"` → `$0.8990005`). Parsed as `Decimal`, divided by 100. No float
  until the API boundary.
- **Tokens.** `total_tokens = uncached_input + cache_read + cache_creation(5m+1h)
  + output` (confirmed by row arithmetic), so `input_tokens = total − output`.
  I keep `requests` and `web_search_requests`; cache detail collapses into input.
- **`surface`** = the Claude `product` (`chat`, `claude_code`, `cowork`).

### Gemini (`ingest/gemini.py`)
- **SKU rows folded.** Each billing line is input *or* output for one model
  (`"Gemini 2.5 Flash Text Output Tokens - Predictions"`). I fold the input and
  output rows for the same `(owner, day, project, model)` into one fact.
- **Cost** is already USD (`cost`; `credits` empty here) → `Decimal`.
- **`surface`** = `vertex` (these run as Vertex AI predictions); the agent label
  is available but not needed for the required views.

### Rows → people and groups (attribution)
Everything attributes through the **directory** (`directory.py`), never a
hard-coded map:

| | user | group |
|---|---|---|
| Claude | `actor.user_id` → directory user | `rbac_group_id` → `groups.claude_rbac_group_id` |
| Gemini | `owner` label (email) → directory user | `project.id` → `groups.gcp_project_id` |

Unattributable rows **raise** during ingest rather than being silently dropped —
in this dataset all 22 users and 6 groups reconcile, and a test asserts it.

### Correctness check
The one-model cost totals equal the raw exports to the cent — **$2,830.29**
(Claude) and **$287.84** (Gemini) — asserted in
`tests/test_ingest_mapping.py::test_platform_cost_totals_match_raw_exports`.

### Periods
`last_7_days` / `last_30_days` are anchored to the **end of the data window
(2026-09-28 exclusive)**, not wall-clock today, so results are deterministic and
include the newest full day. ISO weeks (`2026-W36`) and months (`2026-09`) resolve
to half-open `[start, end_exclusive)` ranges.

---

## Permission model — and where it is enforced

**One engine, enforced in code, in two places that agree.**

- **Source of truth:** `service/meridian_service/permissions.py` (`Authorizer`).
  Mirrored in the connector at `connector/src/permissions.ts` so the MCP server
  refuses *before* it ever calls the backend. The service then enforces again,
  independently — **defence in depth**. A bug in one layer does not open the
  other.
- **Two scopes:** `usage:read` and `capabilities:write`. Which roles hold them,
  and the group-visibility rule, come from the **environment manifest** (the
  `environments/*.yaml`, parsed once in `envspec.py`, rendered to JSON by
  provisioning). Nothing is hard-coded per environment.
- **Order of checks:** (1) does the caller's *role* hold the scope? → else a
  denial with `required_scope`. (2) may the caller see *this group*? admins see
  all; others are bounded by the env's `group_visibility` for reads, and **always
  to their own group for writes** (a lead must never toggle another group's
  controls, even in dev where reads are open). (3) for the connector's data
  tools: is `usage-connector` enabled for the group? → else a denial.
- **Denials are a fixed shape** (contract `$defs/Denial`): `{ error:
  "permission_denied", reason, required_scope? }`, HTTP 403 in the API, an MCP
  error result in the connector. **No partial data ever accompanies a denial** —
  tested on both sides (`test_api.py`, `connector/test/tools.test.ts`).

Identity is **simulated**: the API caller is a directory user in the `X-Actor`
header (or `?actor=` for the page); the connector "starts as" `MERIDIAN_ACTOR`.
Role and groups always come from the directory, never the request body or prompt.

The environment grid (from the starter kit), as enforced:

| | dev | staging | prod |
|---|---|---|---|
| `usage:read` roles | member, lead, admin | lead, admin | lead, admin |
| read visibility | any group | own group (admins: all) | own group (admins: all) |
| `capabilities:write` roles | lead, admin | lead, admin | **admin only** |
| write visibility (non-admin) | own group | own group | — |
| `usage-connector` default | all on | all on | **it-platform + clinical-operations only** |
| `code-execution` default | on | off | off |

---

## Platform depth — what I built for, and exactly what I ran it on

**Built for both platforms.** The connector is one MCP server, packaged two ways:

- **Claude** — a **Claude plugin** (`packaging/claude-plugin/`:
  `.claude-plugin/plugin.json` + `.mcp.json`) and a **Claude Desktop / custom
  local connector** registration (`provisioning/out/<env>/claude_desktop_config.json`).
- **Gemini** — a **Gemini CLI extension** (`packaging/gemini-extension/`:
  `gemini-extension.json` + `GEMINI.md` context), rendered per environment at
  `provisioning/out/<env>/gemini-extension.json`.

**Where the usage data comes from on each platform** (and what the exports stand
in for): Claude's figures are the **Enterprise Analytics API**
(`/v1/organizations/analytics/user_usage_report` + `user_cost_report`, daily
buckets grouped by product/model/cost_type). Gemini's are the **Google Cloud
standard billing export** to BigQuery, filtered to `service.description = "Vertex
AI"` and Gemini token SKUs. The README in `starter-kit/` documents both shapes;
the ingest modules cite the exact fields.

**Exactly what I ran it on — honestly:** I exercised the connector over the **real
MCP protocol via an MCP client** (`@modelcontextprotocol/sdk` `Client` +
`StdioClientTransport`, in `connector/scripts/`), spawning the built
`dist/index.js` as a stdio server against the live FastAPI service. That drives
the same `initialize` / `tools/list` / `tools/call` path Claude Desktop and
Gemini CLI use. The full session is in [`docs/TRANSCRIPT.md`](docs/TRANSCRIPT.md).
I generated and validated the host-registration configs for both Claude Desktop
and Gemini CLI, but I did **not** click through the two desktop/CLI apps
themselves in this environment — the registration files are rendered and
schema-checked, not screenshotted.

---

## Key technical decisions (and why)

- **In-memory usage store.** ≈2,300 facts, read-only — no database needed for
  usage. Load at startup, aggregate on demand. The capability *controls*, which
  are written, go to **SQLite** so edits survive a restart and record
  `updated_by`/`updated_at`.
- **`Decimal` money end-to-end**, one rounding at the API boundary (6 dp to keep
  sub-cent Gemini SKUs). Summing floats across thousands of rows would drift.
- **Permission logic duplicated, deliberately.** The connector can't `import` the
  Python engine, so I mirrored it in TypeScript and unit-tested both against the
  same matrix. The alternative (connector trusts the service entirely) fails the
  brief's "enforce in the server, not the prompt."
- **Provisioning renders *resolved* manifests.** The connector never parses YAML;
  it reads a flat JSON manifest with `default_by_group` pre-computed for every
  group. Auditable, and the same renderer feeds the host configs.
- **Deterministic rendered output + `--check` drift gate.** No timestamps, sorted
  keys. CI re-renders and diffs against the committed files, so "nothing is
  hand-edited" is a test, not a promise.

### Two places I overruled the literal brief (flagged on purpose)
1. **The `usage-connector` gate covers the two *data* tools** (`usage_summary`,
   `top_users`), not `capability_status` / `set_capability`. The contract note
   says "every tool"; taken literally, disabling a group's connector would make
   it impossible to *see* or *re-enable* it through the assistant — a deadlock. I
   keep the control plane reachable so an admin can always recover. Documented
   here and in `connector/src/tools.ts`.
2. **Writes are own-group for non-admins even in dev**, where reads are open to
   all groups. Read-everything is fine for a shared dev; letting a Finance lead
   toggle HR's controls is not.

---

## Engineering standards — followed, and skipped

**Followed.** One responsibility per module; a single permission engine; typed
boundaries (Pydantic / Zod + a JSON-Schema tool contract); tests that pin the
*mapping* and the *permission matrix* (the two things most likely to regress
silently), including a cost cross-check against the raw files; deterministic,
drift-checked provisioning; CI running all three (`.github/workflows/ci.yml`);
no secrets; honest ingest (unattributable rows raise).

**Skipped — and acknowledged.**
- **No authentication.** Identity is a trusted header / env var, as the brief
  permits ("simulated"). Real auth is the first item below.
- **Usage store isn't incremental.** Full reload at startup; no pagination,
  windowing, or caching. Fine for 2,300 rows, not for millions.
- **SQLite, single-node.** No migrations, no concurrent-writer story beyond a
  local file; a `set_capability` race would last-write-win.
- **Admin page is intentionally plain** vanilla JS, no build step, no charts
  library — enough to drive and demonstrate the API, not a product UI.
- **Edge cases I see but didn't over-build:** deleted/renamed users mid-window,
  multi-group users (the directory allows it; I attribute by the row's own
  group/project tag, which is unambiguous here), timezone edges (all data is
  UTC-midnight buckets), and ISO-week/month boundaries straddling the window
  (handled by half-open ranges, tested).

---

## How I used AI tools

I built this with Claude Code (the agent) driving, and I want to be precise about
the division of labour, since the brief asks.

- **AI did the mechanical mass:** scaffolding modules, writing the first pass of
  ingest/store/API/connector, the admin page, and the bulk of the tests, plus
  running everything and iterating on failures in the loop.
- **I verified the data claims by running code, not by trusting prose.** The join
  key uniqueness, the token arithmetic, and the cost totals ($2,830.29 /
  $287.84) were each checked against the raw files before being written into
  tests — because an LLM will happily assert a plausible-but-wrong mapping.
- **Things I overruled / corrected:** the `usage-connector` deadlock (the model's
  first cut gated *all* tools; I narrowed it); a real bug where
  `from __future__ import annotations` + a locally-defined Pydantic body made
  FastAPI treat the request body as a query param (moved the model to module
  scope); and MCP `structuredContent` rejecting arrays (wrapped array payloads).
- **Design decisions were mine:** the Python/TS split, the single-engine +
  defence-in-depth permission model, Decimal money, render-and-drift-check
  provisioning, and the two documented overrules above.

This README and the note to team leads are written by me, not pasted from a
model — the brief asked for that, and it's the right call for writing that two
different audiences have to trust.

---

## What I'd do differently with more time

- **Real identity:** OIDC/JWT on the service, the connector presenting a verified
  token instead of starting as an env-var user; map the token's groups/role,
  drop `X-Actor`.
- **Postgres for controls** with an append-only audit table (who/what/when/old→new)
  instead of last-write-wins SQLite; migrations.
- **Incremental ingest** against the real paginated APIs on a schedule, with
  watermarking, into a columnar store; the in-memory aggregation becomes a query.
- **A proper admin UI** with the weekly data as charts (I kept it a table), and
  CSV export for finance.
- **Contract tests from `tools.schema.json`** generating the Zod/Pydantic types so
  the schema is the single source rather than a mirror.
- **One shared permission spec** (e.g. a small declarative policy both runtimes
  load) to remove the Python/TS duplication entirely.

---

## In the real enterprise version

What changes when the real systems exist, and why the seams are already where
they need to be:

- **The identity provider is live.** `directory.py` is the seam. Today it reads
  the SCIM snapshot JSON; in production it's the IdP via SCIM/OIDC, groups and
  roles synced continuously, de-provisioning honoured. The `rbac_group_id` ↔
  group and `gcp_project_id` ↔ group links are exactly the sync keys the IdP
  already pushes into Claude Enterprise and Google Cloud, so attribution doesn't
  change shape — only its freshness. Identity stops being a header and becomes a
  verified token; the permission engine is unchanged.
- **An org-level connector registry exists.** Today provisioning renders host
  configs into files. In production those render into the organisation's
  connector/registry (managed MCP catalogue, Claude Enterprise's connector admin,
  Gemini's extension distribution), with the permissions manifest as the policy
  artifact the registry stores and signs. `render.py` becomes a step that
  publishes to the registry; `--check` becomes the policy gate. Per-environment
  grants (dev/staging/prod) map onto the registry's environment tiers.
- **The platforms' real usage APIs exist.** The two ingest modules become clients
  of the live Enterprise Analytics API and the BigQuery billing export (or the
  Cloud Billing API), paginated and scheduled, with ret/backoff and watermarks.
  The canonical `UsageFact` and everything above it is untouched — the mapping
  logic I validated here is the mapping logic that runs, just fed from the network
  instead of a file.
- **Real infrastructure exists.** The service runs behind the gateway that
  terminates auth; the capability store is Postgres with history; the usage data
  lands in the warehouse and the API serves aggregates from it; the connector is
  distributed and updated through the registry, not a local `dist/`. The module
  boundaries — directory, ingest, permission engine, usage store, capability
  store — are already the service boundaries, so this is substitution behind
  stable interfaces rather than a rewrite.

The honest summary: this repo is the **logic** of the system with **files standing
in for networked systems of record**. The permission model, the mapping, and the
scoping are the parts that have to be right regardless of where the data comes
from — so those are the parts that are tested hardest here.

---

## Repository layout

```
.
├── service/                     # Part A — Python / FastAPI
│   ├── meridian_service/
│   │   ├── ingest/{claude,gemini}.py   # two exports → one model
│   │   ├── models.py  store.py         # UsageFact + aggregation
│   │   ├── directory.py                # IdP stand-in; attribution
│   │   ├── envspec.py                  # parse environments/*.yaml
│   │   ├── capabilities.py             # persisted controls (SQLite)
│   │   ├── permissions.py              # THE permission engine
│   │   ├── periods.py  config.py  context.py
│   │   ├── api.py                      # FastAPI app
│   │   └── static/admin.html           # minimal admin page + user switcher
│   └── tests/                          # 42 tests (mapping, permissions, store, API)
├── connector/                   # Part B — TypeScript MCP server
│   ├── src/{permissions,tools,server,serviceClient,directory,manifest,config,index}.ts
│   ├── test/                           # 14 tests (permission matrix, tool guards)
│   └── scripts/{transcript,call}.mjs   # real MCP client harness
├── provisioning/
│   ├── render.py                       # one command → manifests + host configs, validate, --check
│   └── out/<env>/                      # rendered, committed, drift-checked
├── packaging/
│   ├── claude-plugin/                  # Claude plugin (manifest + .mcp.json)
│   └── gemini-extension/               # Gemini CLI extension (+ GEMINI.md)
├── docs/
│   ├── TRANSCRIPT.md                   # Part B evidence (reproducible)
│   ├── NOTE_TO_TEAM_LEADS.md           # the note to requesters
│   └── LOOM_SCRIPT.md                  # walkthrough talking points
├── .github/workflows/ci.yml            # tests (both) + provisioning --check
├── Makefile
└── starter-kit/                        # provided data, contract, environments (systems of record)
```
