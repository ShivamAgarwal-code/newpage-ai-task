/**
 * The rendered permissions manifest, produced by `provisioning/render.py`.
 *
 * The connector never parses the environment YAML itself — provisioning renders
 * one resolved JSON manifest per environment and the connector reads it. That
 * keeps dev/staging/prod differences in one place and makes "which grants apply"
 * auditable: it is a file, not code.
 */

import { readFileSync } from "node:fs";
import type { Capability, GroupId, Role } from "./types.js";

export interface PermissionsManifest {
  environment: string;
  server_name: string;
  scopes: {
    "usage:read": { roles: Role[]; group_visibility: "all" | "own_group" };
    "capabilities:write": { roles: Role[] };
  };
  capabilities: Record<Capability, { default_by_group: Record<GroupId, boolean> }>;
}

export function loadManifest(path: string): PermissionsManifest {
  const raw = JSON.parse(readFileSync(path, "utf-8"));
  // Minimal structural validation — fail loud rather than mis-enforce.
  if (!raw.scopes?.["usage:read"]?.roles || !raw.scopes?.["capabilities:write"]?.roles) {
    throw new Error(`Malformed permissions manifest at ${path}: missing scope roles`);
  }
  if (!["all", "own_group"].includes(raw.scopes["usage:read"].group_visibility)) {
    throw new Error(`Malformed manifest: bad group_visibility`);
  }
  return raw as PermissionsManifest;
}
