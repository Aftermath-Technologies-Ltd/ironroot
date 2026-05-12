# @ironroot/core

Integrity primitives for IRONROOT, in TypeScript.

This package is a 1:1 port of the integrity-relevant Python modules in the
[IRONROOT](https://github.com/bradkinnard/ironroot) repository:

| Python source                                              | TypeScript target                       |
| ---------------------------------------------------------- | --------------------------------------- |
| `ironroot/domain/{ids,errors,time,invariants}.py`          | `src/domain/*.ts`                       |
| `ironroot/cognition/memory/append_only_store.py`           | `src/memory/appendOnlyStore.ts`         |
| `ironroot/storage/artifacts.py`                            | `src/storage/artifacts.ts`              |
| `ironroot/verification/{integrity,replay,regression_gate,falsification,invariants}.py` | `src/verification/*.ts`     |
| _(new — Node-only)_                                        | `src/storage/ledger.ts` (`Ledger<T>`)   |

Cross-language fixtures (`test/fixtures/canonical_vectors.json`,
`test/fixtures/chain_vectors.json`) are consumed by both this package's
Vitest suite and the Python suite in `tests/cross_language/` of the
IRONROOT repository. They assert byte-identical canonicalization and
hash-chain hashes between the two implementations.

## Public surface

```ts
import {
  // hashing + ids
  hashContent,
  verifyHash,
  generateId,
  generateUuidv7,
  HASH_GENESIS,
  // canonical JSON
  canonicalJson,
  // errors
  IronrootError, IntegrityError, ImmutabilityViolation,
  BudgetExhausted, InvariantViolation, GateFailed, NotFoundError,
  // time
  nowMs, nowIso, withFrozenTime,
  // invariants
  Invariant, checkInvariant,
  BELIEF_HASH_CHAIN, ARTIFACT_INTEGRITY, BUDGET_NOT_NEGATIVE,
  RUN_STATE_MACHINE, STRATEGY_GATE_REQUIRED,
  // belief store (in-memory)
  AppendOnlyBeliefStore, BeliefRecord,
  // artifact store (filesystem, content-addressed)
  ArtifactStore,
  // ledger (SQLite, hash-chained, write-once, generic)
  Ledger, openLedger, LedgerEntry, LedgerHealth, ChainVerification,
  // verification
  verifyArtifactIntegrity, verifyBeliefChain, verifyAllArtifacts,
  computeTraceDigest, computeReplayDigest, verifyReplay, ReplayDigest,
  executeGateSuite, GateResult, GateSuiteResult,
  attemptFalsification, FalsificationAttempt,
  checkAllInvariants, anyFailed, InvariantCheckResult,
} from "@ironroot/core";
```

## `Ledger<TPayload>` — Dossier integration contract

The SQLite ledger is generic over payload type so that consumers retain
ownership of their domain entry schema. For example,
[Dossier](https://github.com/bradkinnard/dossier) parameterizes it with
`DossierEntry`:

```ts
import { Ledger, HASH_GENESIS, generateUuidv7, sha256 as _ } from "@ironroot/core";
import type { DossierEntry } from "./types/index.js";

const ledger = new Ledger<DossierEntry>(".dossier/ledger.db");

const entry = ledger.write({
  pr_url: "https://github.com/x/y/pull/1",
  commit_sha: "abc123",
  gate_results: [{ name: "lint", passed: true }],
  // ...other DossierEntry fields
});

const { valid, brokenLinks } = ledger.verifyChain();
```

**Contract guarantees**

- `Ledger.write` is write-once. Every entry's `prevHash` is the sha256 of
  the canonical JSON of the previous entry (or `HASH_GENESIS` for the
  first entry). Entries cannot be modified or deleted in-place.
- `canonicalJson` sorts object keys lexicographically and uses
  no-whitespace separators. The Python reference implementation in
  `tests/cross_language/` agrees byte-for-byte under all fixtures.
- `sha256` is SHA-256 over UTF-8 encoded canonical JSON.
- `generateUuidv7` produces RFC 9562 UUIDv7 strings (48-bit ms timestamp,
  version 7, variant `10`, 74 random bits).
- `HASH_GENESIS = "0".repeat(64)`.
- Signing is **out of scope** for `@ironroot/core`. Dossier may layer its
  own signing (HMAC, Sigstore, etc.) on top — the ledger does not verify
  signatures.

## Development

```sh
npm install
npm run build
npm test
```

## License

MIT.
