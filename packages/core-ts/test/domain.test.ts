import { describe, it, expect } from "vitest";
import {
  AppendOnlyBeliefStore,
  hashContent,
  verifyHash,
  generateUuidv7,
} from "../src/index.js";

describe("hashContent / verifyHash", () => {
  it("hashes bytes consistently", () => {
    const h1 = hashContent(Buffer.from("hello"));
    const h2 = hashContent("hello");
    expect(h1).toBe(h2);
    expect(h1).toBe("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
  });

  it("verifyHash detects mismatch", () => {
    const h = hashContent("hello");
    expect(verifyHash("hello", h)).toBe(true);
    expect(verifyHash("world", h)).toBe(false);
  });
});

describe("generateUuidv7", () => {
  it("produces v7 UUIDs with correct format", () => {
    const u = generateUuidv7();
    expect(u).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
  it("generates unique values", () => {
    const a = generateUuidv7();
    const b = generateUuidv7();
    expect(a).not.toBe(b);
  });
});

describe("AppendOnlyBeliefStore", () => {
  it("links records by parent hash", () => {
    const s = new AppendOnlyBeliefStore();
    const r1 = s.append(Buffer.from("a"), "agt_1", "run_1", 0.9);
    const r2 = s.append(Buffer.from("b"), "agt_1", "run_1", 0.9);
    expect(r1.parentHash).toBeNull();
    expect(r2.parentHash).toBe(r1.contentHash);
    expect(s.verifyChain()).toBe(true);
  });

  it("listAll returns chain order", () => {
    const s = new AppendOnlyBeliefStore();
    s.append(Buffer.from("a"), "agt", "run", 1);
    s.append(Buffer.from("b"), "agt", "run", 1);
    s.append(Buffer.from("c"), "agt", "run", 1);
    const all = s.listAll();
    expect(all.map((r) => Buffer.from(r.content).toString())).toEqual(["a", "b", "c"]);
  });
});
