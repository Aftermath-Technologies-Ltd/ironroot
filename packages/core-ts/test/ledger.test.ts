import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Ledger, HASH_GENESIS, hashContent, canonicalJson } from "../src/index.js";

interface Payload {
  msg: string;
  n: number;
}

let dir: string;
let ledger: Ledger<Payload>;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "ledger-"));
  ledger = new Ledger<Payload>(join(dir, "ledger.db"));
});
afterEach(() => {
  ledger.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("Ledger", () => {
  it("writes entries with chained prev_hash", () => {
    const e1 = ledger.write({ msg: "a", n: 1 });
    const e2 = ledger.write({ msg: "b", n: 2 });
    const e3 = ledger.write({ msg: "c", n: 3 });

    expect(e1.prevHash).toBe(HASH_GENESIS);
    expect(e2.prevHash).toBe(hashContent(canonicalJson(e1)));
    expect(e3.prevHash).toBe(hashContent(canonicalJson(e2)));

    expect(ledger.count()).toBe(3);
  });

  it("getById returns the same entry", () => {
    const e = ledger.write({ msg: "x", n: 42 });
    const r = ledger.getById(e.entryId);
    expect(r).not.toBeNull();
    expect(r!.payload.msg).toBe("x");
    expect(r!.payload.n).toBe(42);
  });

  it("verifyChain succeeds on a clean chain", () => {
    ledger.write({ msg: "a", n: 1 });
    ledger.write({ msg: "b", n: 2 });
    const v = ledger.verifyChain();
    expect(v.valid).toBe(true);
    expect(v.brokenLinks).toEqual([]);
  });

  it("getHealth reports counts and last timestamp", () => {
    ledger.write({ msg: "a", n: 1 });
    ledger.write({ msg: "b", n: 2 });
    const h = ledger.getHealth();
    expect(h.totalEntries).toBe(2);
    expect(h.chainIntact).toBe(true);
    expect(h.lastEntryTimestamp).not.toBeNull();
  });

  it("getRange returns entries in created_at order", () => {
    ledger.write({ msg: "a", n: 1 });
    ledger.write({ msg: "b", n: 2 });
    ledger.write({ msg: "c", n: 3 });
    const all = ledger.getRange();
    expect(all.map((e) => e.payload.msg)).toEqual(["a", "b", "c"]);
  });

  it("persists across reopens", () => {
    const e = ledger.write({ msg: "persist", n: 7 });
    ledger.close();
    const reopened = new Ledger<Payload>(join(dir, "ledger.db"));
    try {
      const r = reopened.getById(e.entryId);
      expect(r).not.toBeNull();
      expect(r!.payload.msg).toBe("persist");
      expect(reopened.verifyChain().valid).toBe(true);
    } finally {
      reopened.close();
    }
  });
});
