import { generateId } from "../domain/ids.js";
import { nowIso } from "../domain/time.js";

export interface GateResult {
  readonly gateName: string;
  readonly passed: boolean;
  readonly artifactId: string | null;
  readonly details: string;
}

export interface GateSuiteResult {
  readonly gateBundleId: string;
  readonly runId: string;
  readonly overallStatus: "passed" | "failed";
  readonly gates: readonly GateResult[];
  readonly createdAt: string;
}

export function executeGateSuite(
  runId: string,
  replayOk: boolean,
  integrityOk: boolean,
  invariantsOk: boolean,
  regressionOk: boolean,
): GateSuiteResult {
  const gates: GateResult[] = [
    {
      gateName: "replay",
      passed: replayOk,
      artifactId: null,
      details: replayOk ? "" : "replay determinism check failed",
    },
    {
      gateName: "integrity",
      passed: integrityOk,
      artifactId: null,
      details: integrityOk ? "" : "integrity check failed",
    },
    {
      gateName: "invariants",
      passed: invariantsOk,
      artifactId: null,
      details: invariantsOk ? "" : "invariant violation detected",
    },
    {
      gateName: "regression",
      passed: regressionOk,
      artifactId: null,
      details: regressionOk ? "" : "regression tests failed",
    },
  ];

  const allPassed = gates.every((g) => g.passed);
  return {
    gateBundleId: generateId("gat"),
    runId,
    overallStatus: allPassed ? "passed" : "failed",
    gates,
    createdAt: nowIso(),
  };
}
