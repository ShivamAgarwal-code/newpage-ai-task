/**
 * Shared types for the connector. These mirror the Part A service and the
 * tool contract (contracts/tools.schema.json).
 */

export type Role = "member" | "team_lead" | "platform_admin";

export const GROUP_IDS = [
  "clinical-operations",
  "regulatory-affairs",
  "finance",
  "hr",
  "medical-writing",
  "it-platform",
] as const;
export type GroupId = (typeof GROUP_IDS)[number];

export const CAPABILITIES = ["usage-connector", "web-search", "code-execution"] as const;
export type Capability = (typeof CAPABILITIES)[number];

export interface User {
  user_id: string;
  email: string;
  name: string;
  role: Role;
  group_ids: string[];
}

export interface Group {
  group_id: string;
  name: string;
}

/** The structured denial shape every tool emits on refusal (contract $defs/Denial). */
export interface Denial {
  error: "permission_denied";
  reason: string;
  required_scope?: string;
}

export const USAGE_READ = "usage:read";
export const CAPABILITIES_WRITE = "capabilities:write";

export function denial(reason: string, requiredScope?: string): Denial {
  const d: Denial = { error: "permission_denied", reason };
  if (requiredScope) d.required_scope = requiredScope;
  return d;
}
