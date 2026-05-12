import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { canonicalJson, hashContent, HASH_GENESIS } from "../src/index.js";

const FIXTURES = join(__dirname, "fixtures");

describe("canonical vectors (cross-language)", () => {
  const vectors = JSON.parse(
    readFileSync(join(FIXTURES, "canonical_vectors.json"), "utf-8"),
  ) as { name: string; input: unknown; canonical: string }[];

  for (const v of vectors) {
    it(v.name, () => {
      expect(canonicalJson(v.input)).toBe(v.canonical);
    });
  }
});

describe("chain vectors (cross-language)", () => {
  const cases = JSON.parse(readFileSync(join(FIXTURES, "chain_vectors.json"), "utf-8")) as {
    name: string;
    payloads: unknown[];
    expectedHashes?: string[];
  }[];

  for (const c of cases) {
    it(c.name, () => {
      let prevHash = HASH_GENESIS;
      const hashes: string[] = [];
      c.payloads.forEach((payload, i) => {
        const entry = {
          entryId: `fixture-${String(i).padStart(8, "0")}`,
          prevHash,
          payload,
          createdAt: "2024-01-01T00:00:00.000Z",
        };
        const serialized = canonicalJson(entry);
        const h = hashContent(serialized);
        hashes.push(h);
        prevHash = h;
      });
      if (c.expectedHashes) {
        expect(hashes).toEqual(c.expectedHashes);
      }
      expect(hashes).toHaveLength(c.payloads.length);
    });
  }
});
