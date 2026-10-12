# Part B — transcript

The connector running as a real MCP server over stdio, driven by a small MCP
client harness (`connector/scripts/transcript.mjs` and `call.mjs`) against the
Part A service in the **prod** environment. Reproduce with:

```bash
# terminal 1
cd service && MERIDIAN_ENV=prod .venv/bin/uvicorn meridian_service.api:app --port 8000
# terminal 2
cd connector
node scripts/transcript.mjs priya.nair@meridianls.example   prod   # team lead
node scripts/transcript.mjs chloe.dubois@meridianls.example prod   # platform admin
```

Each tool result is either the data payload (`OK`) or the contract `Denial`
shape (`DENIED`). Denials are produced **in the server**, before any backend
call — a denied read never fetches data.

---

## 1 · Team lead — Priya Nair (`clinical-operations`)

**Allowed read — own group**

```
▶ usage_summary({"period":"2026-09"})
  OK  {"group":"clinical-operations",
       "period":{"start":"2026-09-01","end_exclusive":"2026-10-01"},
       "platforms":[
         {"platform":"claude","requests":1087,"input_tokens":4411485,"output_tokens":661995,"total_tokens":5073480,"cost_usd":67.950677},
         {"platform":"gemini","requests":null,"input_tokens":5001153,"output_tokens":1525880,"total_tokens":6527033,"cost_usd":9.717985}],
       "totals":{"total_tokens":11600513,"cost_usd":77.668662}}

▶ top_users({"period":"2026-09","limit":3})
  OK  [Priya Nair 6,637,296 tok · $34.87,
       Aisha Rahman 2,847,206 tok · $23.76,
       Tomasz Kowalski 1,272,359 tok · $17.92]
```

**Denied cross-group read — structured denial, no data**

```
▶ usage_summary({"group":"finance","period":"2026-09"})
  DENIED  {"error":"permission_denied",
           "reason":"Not permitted to view group 'finance'. You may view: [\"clinical-operations\"]."}
```

**Denied write — team lead lacks `capabilities:write` in prod**

```
▶ set_capability({"group":"clinical-operations","capability":"web-search","enabled":false})
  DENIED  {"error":"permission_denied",
           "reason":"Role 'team_lead' may not change capability controls in the prod environment.",
           "required_scope":"capabilities:write"}
```

**Capability status — own group (allowed)**

```
▶ capability_status({})
  OK  [usage-connector: enabled, web-search: enabled, code-execution: disabled]
```

---

## 2 · Platform admin — Chloe Dubois (`it-platform`)

Same calls, admin identity — the mirror image:

```
▶ usage_summary({"period":"2026-09"})                 OK  (it-platform: 114,178,087 tok · $1,022.35)
▶ usage_summary({"group":"regulatory-affairs",...})   DENIED  usage-connector disabled for 'regulatory-affairs'
▶ set_capability({"group":"clinical-operations",...}) OK  updated_by=chloe.dubois@…, updated_at=…
▶ set_capability({"group":"finance","capability":"code-execution","enabled":true})  OK
```

Note the admin's cross-group read of `regulatory-affairs` is **still** denied —
not by visibility (an admin sees every group) but by the **Part A capability
control**: `usage-connector` is disabled by default for that group in prod. The
denial reason says so. The admin *can* write any group's controls.

---

## 3 · The Part A control gates the assistant

An admin turns `usage-connector` **off** for `clinical-operations`; the lead's
read is then refused by the connector, and restored when it is turned back on:

```
chloe → set_capability(clinical-operations, usage-connector, false)   OK
priya → usage_summary(period=2026-09)
  DENIED  {"error":"permission_denied",
           "reason":"The usage-connector capability is disabled for group 'clinical-operations'."}
chloe → set_capability(clinical-operations, usage-connector, true)    OK
priya → usage_summary(period=2026-09)                                 OK  (data returns)
```

This is the loop the brief asks for: the per-group control set in Part A (by an
admin, persisted) is honoured by the connector before it answers.
