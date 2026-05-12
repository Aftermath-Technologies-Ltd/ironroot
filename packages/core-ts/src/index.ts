/**
 * @ironroot/core
 *
 * Integrity primitives ported from the Python IRONROOT codebase:
 *   - sha256 content hashing + UUIDv7 ids
 *   - deterministic canonical-JSON serialization
 *   - append-only in-memory belief store with hash chain
 *   - content-addressed filesystem artifact store with write-once enforcement
 *   - SQLite-backed Ledger<T> with hash-chained, write-once entries
 *   - verification helpers (integrity, replay, regression gates, invariants)
 *
 * Cross-language fixtures in `test/fixtures/` assert byte-identical
 * canonicalization and chain hashes between this package and the Python
 * implementation.
 */

export * from "./domain/errors.js";
export * from "./domain/ids.js";
export * from "./domain/time.js";
export * from "./domain/invariants.js";
export { canonicalJson } from "./domain/canonical.js";

export { AppendOnlyBeliefStore, type BeliefRecord } from "./memory/appendOnlyStore.js";
export { ArtifactStore } from "./storage/artifacts.js";
export {
  Ledger,
  openLedger,
  type LedgerEntry,
  type LedgerHealth,
  type ChainVerification,
} from "./storage/ledger.js";

export {
  verifyArtifactIntegrity,
  verifyBeliefChain,
  verifyAllArtifacts,
} from "./verification/integrity.js";
export {
  computeTraceDigest,
  computeReplayDigest,
  verifyReplay,
  type ReplayDigest,
} from "./verification/replay.js";
export {
  executeGateSuite,
  type GateResult,
  type GateSuiteResult,
} from "./verification/regressionGate.js";
export {
  attemptFalsification,
  type FalsificationAttempt,
} from "./verification/falsification.js";
export {
  checkAllInvariants,
  anyFailed,
  type InvariantCheckResult,
} from "./verification/invariants.js";
