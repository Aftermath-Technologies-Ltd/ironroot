/**
 * Deterministic JSON canonicalization.
 *
 * Rules:
 *   - object keys are sorted lexicographically (UTF-16 code-unit order)
 *   - arrays preserve order
 *   - undefined and function values are omitted (same as JSON.stringify)
 *   - keys whose values become undefined are dropped
 *   - no whitespace
 *
 * This must remain byte-identical to the Python reference implementation
 * in `packages/core-ts/test/fixtures/` so that hash chains agree across
 * languages.
 */
export function canonicalJson(value: unknown): string {
  return stringify(value) ?? "null";
}

function stringify(value: unknown): string | undefined {
  if (value === null) return "null";
  if (value === undefined) return undefined;

  switch (typeof value) {
    case "boolean":
      return value ? "true" : "false";
    case "number": {
      if (!Number.isFinite(value)) {
        throw new TypeError("canonicalJson: non-finite number is not representable");
      }
      return JSON.stringify(value);
    }
    case "string":
      return JSON.stringify(value);
    case "bigint":
      return value.toString();
    case "object":
      break;
    default:
      return undefined;
  }

  if (Array.isArray(value)) {
    const items = value.map((v) => stringify(v) ?? "null");
    return `[${items.join(",")}]`;
  }

  if (value instanceof Uint8Array) {
    return JSON.stringify(Buffer.from(value).toString("base64"));
  }

  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  const parts: string[] = [];
  for (const k of keys) {
    const v = stringify(obj[k]);
    if (v === undefined) continue;
    parts.push(`${JSON.stringify(k)}:${v}`);
  }
  return `{${parts.join(",")}}`;
}
