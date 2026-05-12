import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

export type IdPrefix = "run" | "agt" | "bel" | "art" | "str" | "inc" | "gat";

let lastTsMs = 0;
let counter = 0;

export function generateId(prefix: IdPrefix): string {
  const tsMs = Date.now();
  if (tsMs === lastTsMs) {
    counter += 1;
  } else {
    lastTsMs = tsMs;
    counter = 0;
  }

  const tsBuf = Buffer.alloc(6);
  // 48-bit big-endian timestamp
  tsBuf.writeUIntBE(tsMs, 0, 6);

  const counterBuf = Buffer.alloc(2);
  counterBuf.writeUInt16BE(counter & 0xffff, 0);

  const randBuf = randomBytes(6);

  return `${prefix}_${Buffer.concat([tsBuf, counterBuf, randBuf]).toString("hex")}`;
}

export function hashContent(data: Buffer | Uint8Array | string): string {
  const buf = typeof data === "string" ? Buffer.from(data, "utf8") : Buffer.from(data);
  return createHash("sha256").update(buf).digest("hex");
}

export function verifyHash(data: Buffer | Uint8Array | string, expectedHash: string): boolean {
  const actual = hashContent(data);
  if (actual.length !== expectedHash.length) return false;
  try {
    return timingSafeEqual(Buffer.from(actual, "hex"), Buffer.from(expectedHash, "hex"));
  } catch {
    return false;
  }
}

/**
 * UUIDv7: 48-bit unix ms timestamp, version 7, 62 bits of randomness.
 * Hex digest formatted as 8-4-4-4-12.
 */
export function generateUuidv7(): string {
  const now = Date.now();
  const rand = randomBytes(10);

  const ms = now.toString(16).padStart(12, "0");
  const timeHi = ms.substring(0, 8);
  const timeMid = ms.substring(8, 12);

  // version 7 in high nibble of byte 6, two random nibbles after
  const verAndRand = `7${(rand[0] & 0x0f).toString(16)}${rand[1].toString(16).padStart(2, "0")}`;

  // variant 10xx in high bits of byte 8
  const variantByte = (rand[2] & 0x3f) | 0x80;
  const clockSeq =
    variantByte.toString(16).padStart(2, "0") + rand[3].toString(16).padStart(2, "0");

  const node = Array.from(rand.slice(4, 10))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return `${timeHi}-${timeMid}-${verAndRand}-${clockSeq}-${node}`;
}

/**
 * 64 zero hex digits. Used as the parent hash of the first entry in a chain.
 */
export const HASH_GENESIS = "0".repeat(64);
