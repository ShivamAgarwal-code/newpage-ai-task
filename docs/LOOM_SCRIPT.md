# Loom walkthrough — talking points (~6–8 min)

A suggested script for the recording. Keep the service running on `:8000` and
have the admin page open in a browser.

## 0 · Opening (20s)
- "This is the Meridian usage connector. Two parts: a Python service that ingests
  Claude and Gemini usage into one model with a scoped API and admin page, and a
  TypeScript MCP connector that exposes it inside the assistant — scoped to who
  you are."

## 1 · The mapping — the backend craft (90s)
- Open `service/meridian_service/ingest/claude.py` and `gemini.py`.
- "Two messy exports. Claude is per-user daily tokens, cost in a *separate* file
  as cents strings; I join them 1:1 on user×day×product×model and add the web-
  search cost rows. Gemini is Google billing — input and output are separate SKU
  rows per project; I fold them back together, attribute by project→group and
  owner-label→user."
- "One canonical `UsageFact`. Money is Decimal end-to-end; I verified the totals
  match the raw files to the cent — $2,830.29 Claude, $287.84 Gemini."

## 2 · The admin page + permission model (120s)
- In the browser, switch the user to **Priya (team lead)**: show her own group's
  usage, platforms, weekly split, top users. Toggle the period.
- Switch group to **finance** → show the red denial banner. "She can't see other
  groups."
- Switch to **Chloe (admin)** → every group visible; toggle a capability and show
  `updated_by` / `updated_at`.
- Open `service/meridian_service/permissions.py`: "One engine. Scope first, then
  visibility. Every read and write goes through it; the API and the MCP server
  both call the same shape of check. This is the part I wanted to be impossible
  to talk around."

## 3 · The connector inside the assistant (120s)
- Run `node connector/scripts/transcript.mjs priya.nair@meridianls.example prod`.
- Walk the output: allowed own-group read; denied cross-group (structured denial,
  no data); denied write (`required_scope`).
- "Enforcement is in the server, not the prompt — the denial happens before any
  backend call. And the service enforces again independently: defence in depth."
- Show the capability-gate demo (scenario 3 in `docs/TRANSCRIPT.md`): admin turns
  `usage-connector` off for a group → the lead's read is refused → back on → it
  works. "That's the Part A control closing the loop into the assistant."

## 4 · Provisioning + distribution (90s)
- Run `python provisioning/render.py` then `--check`.
- "One command renders the permissions manifest and the Claude/Gemini host
  configs for dev, staging and prod from the environment files. `--check`
  validates and fails on drift — CI runs it, so nothing is hand-edited."
- Show `packaging/claude-plugin` and `packaging/gemini-extension`.

## 5 · Decisions I'd flag + real-enterprise (60s)
- "Two decisions I'd call out: I gate the *data* tools on the usage-connector
  switch but keep capability_status/set_capability reachable so an admin can't
  lock themselves out; and writes are always own-group for non-admins even where
  reads are open. Both are in the README."
- "In the real version the directory is the live IdP via SCIM/OIDC, identity is a
  verified token not a header, the capability store is Postgres with history, and
  the exports are the real paginated APIs on a schedule. The seams are already
  there — directory, permission engine, ingest are each one module."

## 6 · Close (15s)
- "Everything runs from a clean clone: `make setup`, `make test`, `make serve`.
  Tests are green, provisioning validates, and the transcript is reproducible."
