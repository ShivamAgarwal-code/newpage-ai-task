/**
 * End-to-end demonstration / transcript generator for Part B.
 *
 * Spawns the built connector as a real MCP server over stdio (as a chosen
 * directory user, against a running Part A service) and exercises the required
 * scenarios: an allowed read, a denied cross-group read, and a denied write —
 * plus an admin write that succeeds. Prints a readable transcript.
 *
 * Usage:
 *   node scripts/transcript.mjs <actor-email> [env]
 *   # requires the Part A service running at MERIDIAN_SERVICE_URL (default :8000)
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const actor = process.argv[2] ?? "priya.nair@meridianls.example";
const env = process.argv[3] ?? "prod";
const serviceUrl = process.env.MERIDIAN_SERVICE_URL ?? "http://127.0.0.1:8000";

function line() {
  console.log("─".repeat(72));
}

async function call(client, name, args) {
  console.log(`\n▶ ${name}(${JSON.stringify(args)})`);
  const res = await client.callTool({ name, arguments: args });
  const payload = res.structuredContent ?? res.content?.[0]?.text;
  const tag = res.isError ? "DENIED " : "OK     ";
  console.log(`  ${tag} ${JSON.stringify(payload)}`);
  return res;
}

async function main() {
  const transport = new StdioClientTransport({
    command: "node",
    args: [resolve(REPO, "connector", "dist", "index.js")],
    env: {
      ...process.env,
      MERIDIAN_ENV: env,
      MERIDIAN_ACTOR: actor,
      MERIDIAN_SERVICE_URL: serviceUrl,
      MERIDIAN_MANIFEST: resolve(REPO, "provisioning", "out", env, "permissions.json"),
      MERIDIAN_DIRECTORY: resolve(REPO, "starter-kit", "data", "directory"),
    },
    stderr: "inherit",
  });

  const client = new Client({ name: "transcript-harness", version: "0.1.0" });
  await client.connect(transport);

  line();
  console.log(`Connected. Acting as ${actor} in '${env}'.`);
  const tools = await client.listTools();
  console.log("Tools:", tools.tools.map((t) => t.name).join(", "));
  line();

  console.log("\n# 1) Allowed read — own group");
  await call(client, "usage_summary", { period: "2026-09" });
  await call(client, "top_users", { period: "2026-09", limit: 3 });

  console.log("\n# 2) Denied cross-group read — structured denial, no data");
  await call(client, "usage_summary", { group: "finance", period: "2026-09" });

  console.log("\n# 3) Denied write — team lead lacks capabilities:write in prod");
  await call(client, "set_capability", {
    group: "clinical-operations",
    capability: "web-search",
    enabled: false,
  });

  console.log("\n# 4) Capability status — own group");
  await call(client, "capability_status", {});

  console.log("\n# 5) Another group's usage — lead: DENIED, admin: OK");
  await call(client, "usage_summary", { group: "regulatory-affairs", period: "2026-09" });

  console.log("\n# 6) Admin write — lead: DENIED, admin: OK (persists + attributes)");
  await call(client, "set_capability", {
    group: "finance",
    capability: "code-execution",
    enabled: true,
  });

  line();
  await client.close();
}

main().catch((err) => {
  console.error("transcript failed:", err);
  process.exit(1);
});
