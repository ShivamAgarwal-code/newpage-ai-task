# Meridian Usage — Claude plugin

Packages the Part B MCP connector as a Claude plugin so it can be distributed
through Claude Code / Claude Desktop the way the platform team ships any
connector.

## Layout

```
claude-plugin/
├── .claude-plugin/plugin.json   # plugin manifest (name, version, author)
└── .mcp.json                    # registers the "meridian-usage" MCP server
```

`.mcp.json` launches the built connector (`connector/dist/index.js`) over stdio.
The `env` block is what scopes the server: it starts as a directory user
(`MERIDIAN_ACTOR`) and loads the rendered per-environment permissions manifest
(`MERIDIAN_MANIFEST`). The server enforces scope and visibility from those — the
prompt cannot widen them.

## Install (local MCP server / custom connector)

1. Build the connector and render the manifests (see the repo root README):
   ```bash
   (cd connector && npm ci && npm run build)
   python provisioning/render.py
   ```
2. Point the plugin at this repo. The manifests use a `${MERIDIAN_REPO}`
   placeholder; export it (or substitute it in a copy):
   ```bash
   export MERIDIAN_REPO=/absolute/path/to/this/repo
   ```
3. Start the Part A service (the connector calls it):
   ```bash
   (cd service && MERIDIAN_ENV=prod .venv/bin/uvicorn meridian_service.api:app --port 8000)
   ```
4. Register the plugin.
   - **Claude Desktop** reads `claude_desktop_config.json`. The per-environment
     version is rendered for you at
     `provisioning/out/<env>/claude_desktop_config.json` — merge its `mcpServers`
     block into your `claude_desktop_config.json` (substituting `${MERIDIAN_REPO}`).
   - **Claude Code** loads `.mcp.json` from a plugin directory; add this folder as
     a plugin (or `claude mcp add` the same command/env).

> The rendered `provisioning/out/<env>/claude_desktop_config.json` and this
> `.mcp.json` are the same registration; provisioning is the source of truth and
> produces one per environment (dev/staging/prod differ only in `MERIDIAN_ENV`
> and the manifest path).

## Try it

In Claude, ask: *"What was clinical-operations' AI usage in 2026-09?"* →
`usage_summary`. As a team lead you see only your own group; ask for another
group and you get a structured denial, not data.
