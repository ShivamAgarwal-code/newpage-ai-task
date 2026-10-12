# Meridian Usage — Gemini CLI extension

Packages the Part B MCP connector as a [Gemini CLI extension]. A Gemini CLI
extension is a directory containing `gemini-extension.json` (which registers one
or more MCP servers) and an optional context file.

## Layout

```
gemini-extension/
├── gemini-extension.json   # registers the "meridian-usage" MCP server + context file
└── GEMINI.md               # context injected into the model when the extension loads
```

## Install

1. Build the connector and render manifests (repo root README):
   ```bash
   (cd connector && npm ci && npm run build)
   python provisioning/render.py
   ```
2. Install the extension. Gemini CLI loads extensions from
   `~/.gemini/extensions/<name>/`:
   ```bash
   export MERIDIAN_REPO=/absolute/path/to/this/repo
   mkdir -p ~/.gemini/extensions/meridian-usage
   # use the per-environment rendered manifest (dev/staging/prod):
   envsubst < provisioning/out/prod/gemini-extension.json \
     > ~/.gemini/extensions/meridian-usage/gemini-extension.json
   cp packaging/gemini-extension/GEMINI.md ~/.gemini/extensions/meridian-usage/
   ```
   (Or `cp` this folder's `gemini-extension.json` and substitute `${MERIDIAN_REPO}` yourself.)
3. Start the Part A service, then run `gemini` and ask about usage.

> `provisioning/out/<env>/gemini-extension.json` is the rendered, per-environment
> source of truth; the file in this folder is the prod-shaped template.

[Gemini CLI extension]: https://ai.google.dev/gemini-api/docs/gemini-cli
