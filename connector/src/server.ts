/**
 * MCP server wiring.
 *
 * Registers the four contract tools on an McpServer and translates the
 * connector's outcome into MCP tool results: a success carries both text and
 * structuredContent; a refusal carries the contract `Denial` shape with
 * `isError: true`, so the model receives a structured denial and no data.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { Connector, Denied } from "./tools.js";
import { CAPABILITIES, Denial, GROUP_IDS, denial } from "./types.js";

const periodSchema = z
  .string()
  .regex(/^(last_7_days|last_30_days|\d{4}-W\d{2}|\d{4}-\d{2})$/, "Invalid period")
  .describe("last_7_days | last_30_days | ISO week (2026-W36) | month (2026-09)");

const groupSchema = z.enum(GROUP_IDS).describe("Group id; defaults to the caller's own group");
const capabilitySchema = z.enum(CAPABILITIES);

function ok(result: unknown) {
  const text = JSON.stringify(result, null, 2);
  // MCP structuredContent must be a JSON *object*. usage_summary / set_capability
  // return objects; top_users / capability_status return arrays, which travel in
  // the text content block (and as structuredContent.items for convenience).
  const structuredContent =
    Array.isArray(result) || result === null || typeof result !== "object"
      ? ({ items: result } as Record<string, unknown>)
      : (result as Record<string, unknown>);
  return {
    content: [{ type: "text" as const, text }],
    structuredContent,
  };
}

function denied(d: Denial) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(d, null, 2) }],
    structuredContent: d as unknown as Record<string, unknown>,
    isError: true,
  };
}

/** Run a connector call, mapping Denied -> contract denial, other errors -> safe denial. */
async function guard(fn: () => Promise<unknown>) {
  try {
    return ok(await fn());
  } catch (err) {
    if (err instanceof Denied) return denied(err.denial);
    return denied(denial(`Unexpected error: ${(err as Error).message}`));
  }
}

export function buildServer(connector: Connector, serverName: string): McpServer {
  const server = new McpServer({ name: serverName, version: "0.1.0" });

  server.registerTool(
    "usage_summary",
    {
      title: "Usage summary",
      description:
        "Per-platform tokens and cost plus totals for a group over a period. " +
        "Defaults to your own group; admins may pass any group.",
      inputSchema: { group: groupSchema.optional(), period: periodSchema },
    },
    async (args) => guard(() => connector.usageSummary(args)),
  );

  server.registerTool(
    "top_users",
    {
      title: "Top users",
      description: "Users in a group ranked by total tokens for a period.",
      inputSchema: {
        group: groupSchema.optional(),
        period: periodSchema,
        limit: z.number().int().min(1).max(25).optional().describe("1–25, default 10"),
      },
    },
    async (args) => guard(() => connector.topUsers(args)),
  );

  server.registerTool(
    "capability_status",
    {
      title: "Capability status",
      description: "Current enable/disable state of each capability for a group.",
      inputSchema: { group: groupSchema.optional() },
    },
    async (args) => guard(() => connector.capabilityStatus(args)),
  );

  server.registerTool(
    "set_capability",
    {
      title: "Set capability",
      description:
        "Enable or disable a capability for a group. Requires the capabilities:write scope.",
      inputSchema: {
        group: groupSchema,
        capability: capabilitySchema,
        enabled: z.boolean(),
      },
    },
    async (args) => guard(() => connector.setCapability(args)),
  );

  return server;
}
