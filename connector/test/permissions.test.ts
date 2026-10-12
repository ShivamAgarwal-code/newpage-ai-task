import assert from "node:assert/strict";
import { test } from "node:test";
import { Authorizer, Denied } from "../src/permissions.js";
import { CHLOE, DANIEL, DEV_MANIFEST, GROUP_IDS, PRIYA, manifest } from "./fixtures.js";

const prod = () => new Authorizer(manifest(), GROUP_IDS);
const dev = () => new Authorizer(DEV_MANIFEST, GROUP_IDS);

test("prod: team lead reads own group only", () => {
  prod().authorizeRead(PRIYA, "clinical-operations"); // no throw
  assert.throws(() => prod().authorizeRead(PRIYA, "finance"), Denied);
});

test("prod: cross-group read denial carries no required_scope (visibility, not scope)", () => {
  try {
    prod().authorizeRead(PRIYA, "finance");
    assert.fail("expected denial");
  } catch (err) {
    assert.ok(err instanceof Denied);
    assert.equal(err.denial.error, "permission_denied");
    assert.equal(err.denial.required_scope, undefined);
    assert.match(err.denial.reason, /finance/);
  }
});

test("prod: member has no read scope", () => {
  try {
    prod().authorizeRead(DANIEL, "clinical-operations");
    assert.fail("expected denial");
  } catch (err) {
    assert.ok(err instanceof Denied);
    assert.equal(err.denial.required_scope, "usage:read");
  }
});

test("prod: admin reads every group", () => {
  const a = prod();
  for (const g of GROUP_IDS) a.authorizeRead(CHLOE, g);
});

test("prod: only admin may write; lead may not", () => {
  assert.throws(() => prod().authorizeWrite(PRIYA, "clinical-operations"), Denied);
  prod().authorizeWrite(CHLOE, "finance"); // admin, any group
});

test("dev: member may read any group, but leads still cannot write other groups", () => {
  dev().authorizeRead(DANIEL, "finance"); // visibility=all
  assert.throws(() => dev().authorizeWrite(PRIYA, "finance"), Denied); // own-group only
  dev().authorizeWrite(PRIYA, "clinical-operations"); // own group ok in dev
});

test("visibleGroups: lead=own, admin=all", () => {
  assert.deepEqual([...prod().visibleGroups(PRIYA)], ["clinical-operations"]);
  assert.equal(prod().visibleGroups(CHLOE).size, GROUP_IDS.length);
});
