import assert from "node:assert/strict";
import { test } from "node:test";
import { Authorizer } from "../src/permissions.js";
import type { ServiceClient, ServiceResponse } from "../src/serviceClient.js";
import { Connector, Denied } from "../src/tools.js";
import { Directory } from "../src/directory.js";
import { CHLOE, GROUP_IDS, PRIYA, manifest } from "./fixtures.js";

function resp<T>(ok: boolean, status: number, body: T): ServiceResponse<T> {
  return { ok, status, body };
}

/** A fake Part A service. Records calls and lets a test flip usage-connector. */
class FakeService {
  calls: string[] = [];
  connectorEnabled = true;

  async usageSummary(group: string, period: string) {
    this.calls.push(`summary:${group}:${period}`);
    return resp(true, 200, { group, period, platforms: [], totals: { total_tokens: 0, cost_usd: 0 } });
  }
  async topUsers(group: string, period: string, limit: number) {
    this.calls.push(`top:${group}:${limit}`);
    return resp(true, 200, []);
  }
  async capabilityStatus(group: string) {
    this.calls.push(`capstatus:${group}`);
    return resp(true, 200, [
      { group, capability: "usage-connector", enabled: this.connectorEnabled },
      { group, capability: "web-search", enabled: true },
      { group, capability: "code-execution", enabled: false },
    ]);
  }
  async setCapability(group: string, capability: string, enabled: boolean) {
    this.calls.push(`set:${group}:${capability}:${enabled}`);
    return resp(true, 200, { group, capability, enabled, updated_at: "now", updated_by: "x" });
  }
}

const dir = new Directory(
  [PRIYA, CHLOE],
  GROUP_IDS.map((g) => ({ group_id: g, name: g })),
);

function connector(actor = PRIYA, fake = new FakeService()) {
  const authorizer = new Authorizer(manifest(), GROUP_IDS);
  const c = new Connector({
    actor,
    directory: dir,
    authorizer,
    service: fake as unknown as ServiceClient,
  });
  return { c, fake };
}

test("usage_summary: allowed own-group read returns data", async () => {
  const { c, fake } = connector();
  const out: any = await c.usageSummary({ period: "2026-09" });
  assert.equal(out.group, "clinical-operations");
  assert.ok(fake.calls.includes("summary:clinical-operations:2026-09"));
});

test("usage_summary: cross-group read is denied and never calls the data endpoint", async () => {
  const { c, fake } = connector();
  await assert.rejects(() => c.usageSummary({ group: "finance", period: "2026-09" }), Denied);
  assert.ok(!fake.calls.some((x) => x.startsWith("summary:")), "must not fetch data");
});

test("usage_summary: honours usage-connector disabled (Part A control)", async () => {
  const fake = new FakeService();
  fake.connectorEnabled = false;
  const { c } = connector(PRIYA, fake);
  await assert.rejects(
    () => c.usageSummary({ period: "2026-09" }),
    (err: unknown) => err instanceof Denied && /usage-connector.*disabled/i.test(err.denial.reason),
  );
  assert.ok(!fake.calls.some((x) => x.startsWith("summary:")), "no data after gate fails");
});

test("capability_status: reachable even when usage-connector is disabled (control plane)", async () => {
  const fake = new FakeService();
  fake.connectorEnabled = false;
  const { c } = connector(PRIYA, fake);
  const rows: any = await c.capabilityStatus({});
  assert.equal(rows.length, 3);
});

test("set_capability: team lead denied in prod (write scope = admin only)", async () => {
  const { c, fake } = connector(PRIYA);
  await assert.rejects(
    () => c.setCapability({ group: "clinical-operations", capability: "web-search", enabled: false }),
    (err: unknown) => err instanceof Denied && err.denial.required_scope === "capabilities:write",
  );
  assert.ok(!fake.calls.some((x) => x.startsWith("set:")), "no write attempted");
});

test("set_capability: admin write calls the service", async () => {
  const { c, fake } = connector(CHLOE);
  await c.setCapability({ group: "finance", capability: "code-execution", enabled: true });
  assert.ok(fake.calls.includes("set:finance:code-execution:true"));
});

test("service 403 is surfaced as a structured Denied", async () => {
  const fake = new FakeService();
  fake.usageSummary = async () =>
    resp(false, 403, { error: "permission_denied", reason: "backend says no" }) as any;
  const { c } = connector(CHLOE, fake);
  await assert.rejects(
    () => c.usageSummary({ group: "finance", period: "2026-09" }),
    (err: unknown) => err instanceof Denied && err.denial.reason === "backend says no",
  );
});
