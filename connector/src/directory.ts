/**
 * The directory — the same users.json / groups.json the service reads.
 *
 * The connector "starts as" a configured user (MERIDIAN_ACTOR) and takes that
 * user's role and groups from here. Identity is simulated but resolved from the
 * system of record, never from the prompt.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Group, User } from "./types.js";

export class Directory {
  private byEmail = new Map<string, User>();
  private byId = new Map<string, User>();
  readonly groups: Group[];
  readonly groupIds: string[];

  constructor(users: User[], groups: Group[]) {
    for (const u of users) {
      this.byEmail.set(u.email.toLowerCase(), u);
      this.byId.set(u.user_id, u);
    }
    this.groups = groups;
    this.groupIds = groups.map((g) => g.group_id);
  }

  static load(directoryDir: string): Directory {
    const usersRaw = JSON.parse(readFileSync(join(directoryDir, "users.json"), "utf-8"));
    const groupsRaw = JSON.parse(readFileSync(join(directoryDir, "groups.json"), "utf-8"));
    const users: User[] = usersRaw.users.map((u: any) => ({
      user_id: u.user_id,
      email: u.email,
      name: u.name,
      role: u.role,
      group_ids: u.group_ids,
    }));
    const groups: Group[] = groupsRaw.groups.map((g: any) => ({
      group_id: g.group_id,
      name: g.name,
    }));
    return new Directory(users, groups);
  }

  resolve(identity: string): User | undefined {
    return this.byId.get(identity) ?? this.byEmail.get(identity.toLowerCase());
  }

  isKnownGroup(groupId: string): boolean {
    return this.groupIds.includes(groupId);
  }
}
