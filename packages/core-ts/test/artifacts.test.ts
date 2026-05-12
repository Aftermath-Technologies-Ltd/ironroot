import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ArtifactStore, IntegrityError, NotFoundError } from "../src/index.js";

let dir: string;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "artifact-"));
});
afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe("ArtifactStore", () => {
  it("stores and retrieves content-addressed", () => {
    const s = new ArtifactStore(dir);
    const h = s.store(Buffer.from("hello world"));
    expect(s.exists(h)).toBe(true);
    expect(Buffer.from(s.retrieve(h)).toString()).toBe("hello world");
    expect(s.verify(h)).toBe(true);
  });

  it("write-once: same data is idempotent", () => {
    const s = new ArtifactStore(dir);
    const h1 = s.store(Buffer.from("abc"));
    const h2 = s.store(Buffer.from("abc"));
    expect(h1).toBe(h2);
  });

  it("retrieve throws NotFoundError for unknown hash", () => {
    const s = new ArtifactStore(dir);
    expect(() => s.retrieve("a".repeat(64))).toThrow(NotFoundError);
  });

  it("detects corruption", () => {
    const s = new ArtifactStore(dir);
    const h = s.store(Buffer.from("original"));
    // corrupt the file on disk
    const path = join(dir, h.slice(0, 4), h, "content");
    writeFileSync(path, "tampered");
    expect(s.verify(h)).toBe(false);
    expect(() => s.retrieve(h)).toThrow(IntegrityError);
    // re-store with the original hash now fails too (existing content doesn't match)
    expect(() => s.store(Buffer.from("original"))).toThrow(IntegrityError);
  });

  it("delete removes artifact", () => {
    const s = new ArtifactStore(dir);
    const h = s.store(Buffer.from("temp"));
    expect(s.delete(h)).toBe(true);
    expect(s.exists(h)).toBe(false);
    expect(s.delete(h)).toBe(false);
  });
});
