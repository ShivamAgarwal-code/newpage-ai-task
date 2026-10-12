import { Directory } from "../src/directory.js";
import type { PermissionsManifest } from "../src/manifest.js";
import type { User } from "../src/types.js";

export const GROUP_IDS = [
  "clinical-operations",
  "regulatory-affairs",
  "finance",
  "hr",
  "medical-writing",
  "it-platform",
];

export function user(partial: Partial<User> & Pick<User, "role" | "group_ids">): User {
  return {
    user_id: partial.user_id ?? "user_test",
    email: partial.email ?? "test@meridianls.example",
    name: partial.name ?? "Test User",
    role: partial.role,
    group_ids: partial.group_ids,
  };
}

export const PRIYA = user({
  user_id: "user_E7691888F28227066DD2FB86",
  email: "priya.nair@meridianls.example",
  name: "Priya Nair",
  role: "team_lead",
  group_ids: ["clinical-operations"],
});

export const DANIEL = user({
  email: "daniel.okafor@meridianls.example",
  role: "member",
  group_ids: ["clinical-operations"],
});

export const CHLOE = user({
  email: "chloe.dubois@meridianls.example",
  name: "Chloe Dubois",
  role: "platform_admin",
  group_ids: ["it-platform"],
});

export function manifest(
  overrides: Partial<PermissionsManifest> = {},
): PermissionsManifest {
  const base: PermissionsManifest = {
    environment: "prod",
    server_name: "meridian-usage",
    scopes: {
      "usage:read": { roles: ["team_lead", "platform_admin"], group_visibility: "own_group" },
      "capabilities:write": { roles: ["platform_admin"] },
    },
    capabilities: {
      "usage-connector": {
        default_by_group: Object.fromEntries(
          GROUP_IDS.map((g) => [g, g === "it-platform" || g === "clinical-operations"]),
        ) as any,
      },
      "web-search": { default_by_group: Object.fromEntries(GROUP_IDS.map((g) => [g, true])) as any },
      "code-execution": {
        default_by_group: Object.fromEntries(GROUP_IDS.map((g) => [g, false])) as any,
      },
    },
  };
  return { ...base, ...overrides, scopes: { ...base.scopes, ...overrides.scopes } };
}

export const DEV_MANIFEST = manifest({
  environment: "dev",
  server_name: "meridian-usage-dev",
  scopes: {
    "usage:read": { roles: ["member", "team_lead", "platform_admin"], group_visibility: "all" },
    "capabilities:write": { roles: ["team_lead", "platform_admin"] },
  },
});
