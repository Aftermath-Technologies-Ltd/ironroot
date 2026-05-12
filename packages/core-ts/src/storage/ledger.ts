import Database from "better-sqlite3";
import { mkdirSync, existsSync } from "node:fs";
import { dirname } from "node:path";
import { canonicalJson } from "../domain/canonical.js";
import { ImmutabilityViolation, IntegrityError } from "../domain/errors.js";
import { HASH_GENESIS, generateUuidv7, hashContent } from "../domain/ids.js";
import { nowIso } from "../domain/time.js";

/**
 * A single ledger entry. `entryId` and `prevHash` are managed by the ledger.
 * Consumers supply only their payload via {@link Ledger.write}.
 */
export interface LedgerEntry<TPayload> {
  readonly entryId: string;
  readonly prevHash: string;
  readonly payload: TPayload;
  readonly createdAt: string;
}

export interface LedgerHealth {
  readonly totalEntries: number;
  readonly lastEntryTimestamp: string | null;
  readonly chainIntact: boolean;
}

export interface ChainVerification {
  readonly valid: boolean;
  readonly brokenLinks: string[];
}

interface Row {
  seq: number;
  id: string;
  prev_hash: string;
  payload: string;
  created_at: string;
}

/**
 * SQLite-backed, hash-chained, write-once ledger.
 *
 * Each entry hashes the canonical-JSON serialization of
 * `{ entryId, prevHash, payload, createdAt }`. The next entry's
 * `prevHash` is the previous entry's hash. The first entry's
 * `prevHash` is {@link HASH_GENESIS}.
 *
 * Generic over payload type so domain-specific entry schemas
 * (e.g. Dossier's `DossierEntry`) live in the consumer package.
 */
export class Ledger<TPayload> {
  private readonly db: Database.Database;

  constructor(dbPath: string) {
    const dir = dirname(dbPath);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    this.db = new Database(dbPath);
    this.db.pragma("journal_mode = WAL");
    this.initialize();
  }

  private initialize(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS entries (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        prev_hash TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_entries_prev_hash ON entries(prev_hash);
      CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at);
    `);
  }

  write(payload: TPayload): LedgerEntry<TPayload> {
    const prevHash = this.getLatestHash();
    const entryId = generateUuidv7();
    const createdAt = nowIso();

    const entry: LedgerEntry<TPayload> = { entryId, prevHash, payload, createdAt };
    const serialized = canonicalJson(entry);

    const existing = this.db.prepare(`SELECT id FROM entries WHERE id = ?`).get(entryId);
    if (existing) {
      throw new ImmutabilityViolation(`entry already exists: ${entryId}`);
    }

    this.db
      .prepare(
        `INSERT INTO entries (id, prev_hash, payload, created_at) VALUES (?, ?, ?, ?)`,
      )
      .run(entryId, prevHash, serialized, createdAt);

    return entry;
  }

  getById(entryId: string): LedgerEntry<TPayload> | null {
    const row = this.db.prepare(`SELECT * FROM entries WHERE id = ?`).get(entryId) as
      | Row
      | undefined;
    return row ? rowToEntry<TPayload>(row) : null;
  }

  getRange(from?: string, to?: string): LedgerEntry<TPayload>[] {
    const clauses: string[] = [];
    const params: string[] = [];
    if (from) {
      clauses.push("created_at >= ?");
      params.push(from);
    }
    if (to) {
      clauses.push("created_at <= ?");
      params.push(to);
    }
    const where = clauses.length > 0 ? `WHERE ${clauses.join(" AND ")}` : "";
    const sql = `SELECT * FROM entries ${where} ORDER BY seq ASC`;
    const rows = this.db.prepare(sql).all(...params) as Row[];
    return rows.map((r) => rowToEntry<TPayload>(r));
  }

  verifyChain(): ChainVerification {
    const rows = this.db.prepare(`SELECT * FROM entries ORDER BY seq ASC`).all() as Row[];
    const brokenLinks: string[] = [];
    let expected = HASH_GENESIS;

    for (const row of rows) {
      if (row.prev_hash !== expected) {
        brokenLinks.push(
          `entry ${row.id}: expected prev_hash ${expected}, got ${row.prev_hash}`,
        );
      }
      const entry = rowToEntry<TPayload>(row);
      const recomputed = canonicalJson(entry);
      if (recomputed !== row.payload) {
        brokenLinks.push(
          `entry ${row.id}: payload not canonical (re-canonicalization differs)`,
        );
      }
      expected = hashContent(row.payload);
    }

    return { valid: brokenLinks.length === 0, brokenLinks };
  }

  getHealth(): LedgerHealth {
    const c = this.db.prepare(`SELECT COUNT(*) as total FROM entries`).get() as {
      total: number;
    };
    const last = this.db
      .prepare(`SELECT created_at FROM entries ORDER BY seq DESC LIMIT 1`)
      .get() as { created_at: string } | undefined;
    const chain = this.verifyChain();
    return {
      totalEntries: c.total,
      lastEntryTimestamp: last?.created_at ?? null,
      chainIntact: chain.valid,
    };
  }

  count(): number {
    const r = this.db.prepare(`SELECT COUNT(*) as total FROM entries`).get() as {
      total: number;
    };
    return r.total;
  }

  /**
   * Detect tamper: re-canonicalize each row and compare to stored payload.
   * Throws IntegrityError on first mismatch.
   */
  assertNoTamper(): void {
    const result = this.verifyChain();
    if (!result.valid) {
      throw new IntegrityError(`ledger tampered: ${result.brokenLinks.join("; ")}`);
    }
  }

  private getLatestHash(): string {
    const last = this.db
      .prepare(`SELECT payload FROM entries ORDER BY seq DESC LIMIT 1`)
      .get() as { payload: string } | undefined;
    if (!last) return HASH_GENESIS;
    return hashContent(last.payload);
  }

  close(): void {
    this.db.close();
  }
}

function rowToEntry<T>(row: Row): LedgerEntry<T> {
  const parsed = JSON.parse(row.payload) as LedgerEntry<T>;
  return parsed;
}

export function openLedger<T>(dbPath: string): Ledger<T> {
  return new Ledger<T>(dbPath);
}
