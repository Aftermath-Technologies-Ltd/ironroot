import { hashContent } from "../domain/ids.js";

export interface ReplayDigest {
  readonly runId: string;
  readonly seed: number;
  readonly traceHash: string;
  readonly artifactHashes: readonly string[];
  readonly beliefChainHash: string;
}

export function computeTraceDigest(events: readonly Uint8Array[]): string {
  const total = events.reduce((acc, e) => acc + e.byteLength, 0);
  const combined = Buffer.alloc(total);
  let off = 0;
  for (const e of events) {
    combined.set(e, off);
    off += e.byteLength;
  }
  return hashContent(combined);
}

export function computeReplayDigest(
  runId: string,
  seed: number,
  traceEvents: readonly Uint8Array[],
  artifactHashes: readonly string[],
  beliefChainHash: string,
): ReplayDigest {
  return {
    runId,
    seed,
    traceHash: computeTraceDigest(traceEvents),
    artifactHashes: Object.freeze([...artifactHashes].sort()),
    beliefChainHash,
  };
}

export function verifyReplay(original: ReplayDigest, replayed: ReplayDigest): boolean {
  if (original.seed !== replayed.seed) return false;
  if (original.traceHash !== replayed.traceHash) return false;
  if (original.beliefChainHash !== replayed.beliefChainHash) return false;
  if (original.artifactHashes.length !== replayed.artifactHashes.length) return false;
  for (let i = 0; i < original.artifactHashes.length; i += 1) {
    if (original.artifactHashes[i] !== replayed.artifactHashes[i]) return false;
  }
  return true;
}
