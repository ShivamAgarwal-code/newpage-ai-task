/**
 * Single-tool MCP call harness — for scripted demos and the transcript.
 *
 *   node scripts/call.mjs <actor-email> <env> <tool> '<json-args>'
 *
 * Spawns the built connector as the given actor and invokes one tool, printing
 * OK/DENIED and the payload. Requires the Part A service running.
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");

const [actor, env, tool, argsJson = "{}"] = process.argv.slice(2);
if (!actor || !env || !tool) {
  console.error("usage: node scripts/call.mjs <actor> <env> <tool> '<json-args>'");
  process.exit(2);
}

const transport = new StdioClientTransport({
  command: "node",
  args: [resolve(REPO, "connector", "dist", "index.js")],
  env: {
    ...process.env,
    MERIDIAN_ENV: env,
    MERIDIAN_ACTOR: actor,
    MERIDIAN_SERVICE_URL: process.env.MERIDIAN_SERVICE_URL ?? "http://127.0.0.1:8000",
    MERIDIAN_MANIFEST: resolve(REPO, "provisioning", "out", env, "permissions.json"),
    MERIDIAN_DIRECTORY: resolve(REPO, "starter-kit", "data", "directory"),
  },
  stderr: "ignore",
});

const client = new Client({ name: "call-harness", version: "0.1.0" });
await client.connect(transport);
const res = await client.callTool({ name: tool, arguments: JSON.parse(argsJson) });
const payload = res.structuredContent ?? res.content?.[0]?.text;
console.log(`${res.isError ? "DENIED" : "OK"}  ${actor} → ${tool}(${argsJson})`);
console.log("  " + JSON.stringify(payload));
await client.close();
