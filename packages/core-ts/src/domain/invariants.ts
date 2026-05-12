import { InvariantViolation } from "./errors.js";

export interface Invariant {
  readonly name: string;
  readonly description: string;
}

export function checkInvariant(invariant: Invariant, condition: boolean, details = ""): void {
  if (!condition) {
    throw new InvariantViolation(invariant.name, details || invariant.description);
  }
}

export const BELIEF_HASH_CHAIN: Invariant = {
  name: "belief_hash_chain",
  description: "every belief must reference its parent hash correctly",
};

export const ARTIFACT_INTEGRITY: Invariant = {
  name: "artifact_integrity",
  description: "stored artifact bytes must match recorded hash",
};

export const BUDGET_NOT_NEGATIVE: Invariant = {
  name: "budget_not_negative",
  description: "resource budgets must never go negative",
};

export const RUN_STATE_MACHINE: Invariant = {
  name: "run_state_machine",
  description: "run phase transitions must follow defined state machine",
};

export const STRATEGY_GATE_REQUIRED: Invariant = {
  name: "strategy_gate_required",
  description: "strategies cannot be promoted without passing gates",
};
