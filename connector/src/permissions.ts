/**
 * Enforcement, in the server — not in the prompt.
 *
 * This mirrors the Python service's permission engine so the connector refuses
 * before any data is fetched. The service enforces again on its side (defence in
 * depth), but a team lead asking for another group's usage is stopped here, with
 * a structured denial and no call to the backend.
 *
 * Order of checks for a read:
 *   1. scope      — role holds usage:read in this environment?
 *   2. visibility — may this caller see this group?
 *   3. capability — is usage-connector enabled for this group? (gate from Part A)
 */

import type { PermissionsManifest } from "./manifest.js";
import {
  CAPABILITIES_WRITE,
  Denial,
  USAGE_READ,
  User,
  denial,
} from "./types.js";

export class Denied extends Error {
  constructor(public readonly denial: Denial) {
    super(denial.reason);
  }
}

export class Authorizer {
  constructor(
    private readonly manifest: PermissionsManifest,
    private readonly allGroupIds: string[],
  ) {}

  private isAdmin(user: User): boolean {
    return user.role === "platform_admin";
  }

  visibleGroups(user: User): Set<string> {
    if (this.isAdmin(user)) return new Set(this.allGroupIds);
    if (this.manifest.scopes[USAGE_READ].group_visibility === "all") {
      return new Set(this.allGroupIds);
    }
    return new Set(user.group_ids);
  }

  defaultGroup(user: User): string {
    return user.group_ids[0];
  }

  resolveGroup(user: User, requested?: string): string {
    return requested ?? this.defaultGroup(user);
  }

  /** Throws Denied if the caller may not read this group. */
  authorizeRead(user: User, groupId: string): void {
    if (!this.manifest.scopes[USAGE_READ].roles.includes(user.role)) {
      throw new Denied(
        denial(
          `Role '${user.role}' does not hold ${USAGE_READ} in the ${this.manifest.environment} environment.`,
          USAGE_READ,
        ),
      );
    }
    if (!this.visibleGroups(user).has(groupId)) {
      const allowed = [...this.visibleGroups(user)].sort();
      throw new Denied(
        denial(`Not permitted to view group '${groupId}'. You may view: ${JSON.stringify(allowed)}.`),
      );
    }
  }

  /** Throws Denied if the caller may not change this group's controls. */
  authorizeWrite(user: User, groupId: string): void {
    if (!this.manifest.scopes[CAPABILITIES_WRITE].roles.includes(user.role)) {
      throw new Denied(
        denial(
          `Role '${user.role}' may not change capability controls in the ${this.manifest.environment} environment.`,
          CAPABILITIES_WRITE,
        ),
      );
    }
    // Non-admins may only write their own group, regardless of read visibility.
    if (!this.isAdmin(user) && !user.group_ids.includes(groupId)) {
      throw new Denied(
        denial(
          `Not permitted to change controls for group '${groupId}'. You may change: ${JSON.stringify(user.group_ids.slice().sort())}.`,
        ),
      );
    }
  }
}
