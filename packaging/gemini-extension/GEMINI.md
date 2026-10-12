# Meridian Usage connector

You have a `meridian-usage` connector that answers questions about AI usage and
cost across Claude and Gemini at Meridian Life Sciences, and manages per-group
capability controls.

Tools:

- `usage_summary(group?, period)` — tokens and cost per platform plus totals.
- `top_users(group?, period, limit?)` — users ranked by total tokens.
- `capability_status(group?)` — current capability switches for a group.
- `set_capability(group, capability, enabled)` — change a switch (admins only).

Notes for answering well:

- `period` is `last_7_days`, `last_30_days`, an ISO week like `2026-W36`, or a
  month like `2026-09`. Relative periods are anchored to the end of the data
  window (2026-09-28).
- `group` defaults to the caller's own group. The connector is scoped: a team
  lead only sees their own group. If a tool returns
  `{"error":"permission_denied", ...}`, relay the `reason` plainly — do not try
  to work around it or retry with a different group.
- Costs are USD. Tokens are whole counts.
