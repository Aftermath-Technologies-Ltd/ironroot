import {
  ARTIFACT_INTEGRITY,
  BELIEF_HASH_CHAIN,
  BUDGET_NOT_NEGATIVE,
  type Invariant,
} from "../domain/invariants.js";

export interface InvariantCheckResult {
  readonly invariant: Invariant;
  readonly passed: boolean;
  readonly details: string;
}

export function checkAllInvariants(
  beliefChainOk: boolean,
  artifactIntegrityOk: boolean,
  budgetOk: boolean,
): InvariantCheckResult[] {
  return [
    {
      invariant: BELIEF_HASH_CHAIN,
      passed: beliefChainOk,
      details: beliefChainOk ? "" : "hash chain verification failed",
    },
    {
      invariant: ARTIFACT_INTEGRITY,
      passed: artifactIntegrityOk,
      details: artifactIntegrityOk ? "" : "artifact integrity check failed",
    },
    {
      invariant: BUDGET_NOT_NEGATIVE,
      passed: budgetOk,
      details: budgetOk ? "" : "budget went negative",
    },
  ];
}

export function anyFailed(results: readonly InvariantCheckResult[]): boolean {
  return results.some((r) => !r.passed);
}
