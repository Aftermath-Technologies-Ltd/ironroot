let frozenTime: number | null = null;

export function nowMs(): number {
  return frozenTime !== null ? Math.floor(frozenTime * 1000) : Date.now();
}

export function nowIso(): string {
  const d = frozenTime !== null ? new Date(frozenTime * 1000) : new Date();
  return d.toISOString();
}

export async function withFrozenTime<T>(timestampSec: number, fn: () => Promise<T> | T): Promise<T> {
  const old = frozenTime;
  frozenTime = timestampSec;
  try {
    return await fn();
  } finally {
    frozenTime = old;
  }
}
