export class IronrootError extends Error {
  readonly code: string;
  constructor(message: string, code = "IRONROOT_ERROR") {
    super(message);
    this.name = "IronrootError";
    this.code = code;
  }
}

export class IntegrityError extends IronrootError {
  constructor(message: string) {
    super(message, "INTEGRITY_ERROR");
    this.name = "IntegrityError";
  }
}

export class ImmutabilityViolation extends IronrootError {
  constructor(message: string) {
    super(message, "IMMUTABILITY_VIOLATION");
    this.name = "ImmutabilityViolation";
  }
}

export class BudgetExhausted extends IronrootError {
  readonly resource: string;
  readonly limit: number;
  readonly used: number;
  constructor(resource: string, limit: number, used: number) {
    super(`budget exhausted: ${resource} limit=${limit} used=${used}`, "BUDGET_EXHAUSTED");
    this.name = "BudgetExhausted";
    this.resource = resource;
    this.limit = limit;
    this.used = used;
  }
}

export class InvariantViolation extends IronrootError {
  readonly invariant: string;
  readonly details: string;
  constructor(invariant: string, details: string) {
    super(`invariant violated: ${invariant} - ${details}`, "INVARIANT_VIOLATION");
    this.name = "InvariantViolation";
    this.invariant = invariant;
    this.details = details;
  }
}

export class GateFailed extends IronrootError {
  readonly gateName: string;
  readonly reason: string;
  constructor(gateName: string, reason: string) {
    super(`gate failed: ${gateName} - ${reason}`, "GATE_FAILED");
    this.name = "GateFailed";
    this.gateName = gateName;
    this.reason = reason;
  }
}

export class NotFoundError extends IronrootError {
  readonly resourceType: string;
  readonly resourceId: string;
  constructor(resourceType: string, resourceId: string) {
    super(`${resourceType} not found: ${resourceId}`, "NOT_FOUND");
    this.name = "NotFoundError";
    this.resourceType = resourceType;
    this.resourceId = resourceId;
  }
}
