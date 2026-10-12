#!/usr/bin/env node
/**
 * Entry point: resolve the configured actor from the directory, load the
 * rendered permissions manifest for the environment, and serve the four tools
 * over stdio. Fails fast (before serving) if the actor is unknown.
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { loadConfig } from "./config.js";
import { Directory } from "./directory.js";
import { loadManifest } from "./manifest.js";
import { Authorizer } from "./permissions.js";
import { ServiceClient } from "./serviceClient.js";
import { buildServer } from "./server.js";
import { Connector } from "./tools.js";

async function main(): Promise<void> {
  const config = loadConfig();
  const directory = Directory.load(config.directoryDir);
  const actor = directory.resolve(config.actor);
  if (!actor) {
    throw new Error(`Unknown actor '${config.actor}' — not found in the directory.`);
  }
  const manifest = loadManifest(config.manifestPath);
  const authorizer = new Authorizer(manifest, directory.groupIds);
  const service = new ServiceClient(config.serviceUrl, actor.email);
  const connector = new Connector({ actor, directory, authorizer, service });

  const server = buildServer(connector, manifest.server_name);
  await server.connect(new StdioServerTransport());
  // stderr is safe for diagnostics; stdout is the MCP channel.
  process.stderr.write(
    `[meridian-usage] ready as ${actor.email} (${actor.role}) in ${manifest.environment}\n`,
  );
}

main().catch((err) => {
  process.stderr.write(`[meridian-usage] fatal: ${(err as Error).message}\n`);
  process.exit(1);
});
