/**
 * Connector configuration, all from the environment so the same binary runs in
 * dev / staging / prod. Paths default to this repo's layout so a local run works
 * straight after `npm run build`.
 */

import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url)); // connector/dist (or src under tsx)
const REPO_ROOT = resolve(HERE, "..", "..");

export interface ConnectorConfig {
  environment: string;
  actor: string;
  serviceUrl: string;
  manifestPath: string;
  directoryDir: string;
}

export function loadConfig(env = process.env): ConnectorConfig {
  const environment = (env.MERIDIAN_ENV ?? "dev").toLowerCase();
  const actor = env.MERIDIAN_ACTOR ?? "";
  if (!actor) {
    throw new Error(
      "MERIDIAN_ACTOR is required: the connector starts as a directory user (email or user_id).",
    );
  }
  return {
    environment,
    actor,
    serviceUrl: env.MERIDIAN_SERVICE_URL ?? "http://127.0.0.1:8000",
    manifestPath:
      env.MERIDIAN_MANIFEST ??
      join(REPO_ROOT, "provisioning", "out", `permissions.${environment}.json`),
    directoryDir:
      env.MERIDIAN_DIRECTORY ?? join(REPO_ROOT, "starter-kit", "data", "directory"),
  };
}
