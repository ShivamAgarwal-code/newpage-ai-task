/**
 * The four tools, with enforcement.
 *
 * Each tool returns either its result payload or a structured `Denial`. The
 * guard order is: resolve the target group (default = caller's own), authorize
 * scope + visibility, then — for the usage *data* tools — honour the
 * `usage-connector` control from Part A. Only then do we call the service.
 *
 * Capability gate — a deliberate narrowing of the brief, documented in the
 * README: `usage-connector` gates the two usage-data tools (`usage_summary`,
 * `top_users`). `capability_status` and `set_capability` are the control plane
 * for the switch itself and are governed by scope/visibility only — otherwise a
 * group whose connector was turned off could never be inspected or turned back
 * on through the assistant (a deadlock).
 */

import { Authorizer, Denied } from "./permissions.js";
import type { Directory } from "./directory.js";
import type { ServiceClient, ServiceResponse } from "./serviceClient.js";
import { Capability, Denial, User, denial } from "./types.js";

export interface ConnectorDeps {
  actor: User;
  directory: Directory;
  authorizer: Authorizer;
  service: ServiceClient;
}

export class Connector {
  constructor(private readonly deps: ConnectorDeps) {}

  get actor(): User {
    return this.deps.actor;
  }

  /** Map a service 403 (already a Denial body) or transport failure into Denied. */
  private unwrap<T>(res: ServiceResponse<T>): T {
    if (res.ok) return res.body;
    if (res.status === 403 && (res.body as any)?.error === "permission_denied") {
      throw new Denied(res.body as unknown as Denial);
    }
    throw new Denied(
      denial(`Upstream service error (${res.status}): ${JSON.stringify(res.body)}`),
    );
  }

  private async assertUsageConnectorEnabled(group: string): Promise<void> {
    const rows = this.unwrap(await this.deps.service.capabilityStatus(group)) as Array<{
      capability: Capability;
      enabled: boolean;
    }>;
    const connector = rows.find((r) => r.capability === "usage-connector");
    if (!connector || !connector.enabled) {
      throw new Denied(
        denial(`The usage-connector capability is disabled for group '${group}'.`),
      );
    }
  }

  async usageSummary(args: { group?: string; period: string }): Promise<unknown> {
    const group = this.deps.authorizer.resolveGroup(this.actor, args.group);
    this.deps.authorizer.authorizeRead(this.actor, group);
    await this.assertUsageConnectorEnabled(group);
    return this.unwrap(await this.deps.service.usageSummary(group, args.period));
  }

  async topUsers(args: { group?: string; period: string; limit?: number }): Promise<unknown> {
    const group = this.deps.authorizer.resolveGroup(this.actor, args.group);
    this.deps.authorizer.authorizeRead(this.actor, group);
    await this.assertUsageConnectorEnabled(group);
    return this.unwrap(await this.deps.service.topUsers(group, args.period, args.limit ?? 10));
  }

  async capabilityStatus(args: { group?: string }): Promise<unknown> {
    const group = this.deps.authorizer.resolveGroup(this.actor, args.group);
    this.deps.authorizer.authorizeRead(this.actor, group);
    return this.unwrap(await this.deps.service.capabilityStatus(group));
  }

  async setCapability(args: {
    group: string;
    capability: Capability;
    enabled: boolean;
  }): Promise<unknown> {
    this.deps.authorizer.authorizeWrite(this.actor, args.group);
    return this.unwrap(
      await this.deps.service.setCapability(args.group, args.capability, args.enabled),
    );
  }
}

export { Denied };
