import { generateId, hashContent } from "../domain/ids.js";
import { nowIso } from "../domain/time.js";

export interface BeliefRecord {
  readonly beliefId: string;
  readonly contentHash: string;
  readonly parentHash: string | null;
  readonly agentId: string;
  readonly runId: string;
  readonly content: Uint8Array;
  readonly confidence: number;
  readonly createdAt: string;
  readonly evidenceArtifactIds: readonly string[];
}

/**
 * In-memory append-only belief store with hash-chain integrity.
 *
 * Port of `ironroot.cognition.memory.append_only_store.AppendOnlyBeliefStore`.
 * Records can only be appended; existing records are never altered. The chain
 * links `parentHash` -> previous record's `contentHash`. `verifyChain`
 * recomputes every hash and every link relation.
 */
export class AppendOnlyBeliefStore {
  private readonly beliefs = new Map<string, BeliefRecord>();
  private readonly chain: string[] = [];
  private readonly hashToId = new Map<string, string>();

  append(
    content: Uint8Array,
    agentId: string,
    runId: string,
    confidence: number,
    evidenceArtifactIds: readonly string[] = [],
  ): BeliefRecord {
    const beliefId = generateId("bel");
    const contentHash = hashContent(content);
    const parentHash = this.chain.length > 0 ? this.chain[this.chain.length - 1]! : null;

    const record: BeliefRecord = {
      beliefId,
      contentHash,
      parentHash,
      agentId,
      runId,
      content,
      confidence,
      createdAt: nowIso(),
      evidenceArtifactIds: Object.freeze([...evidenceArtifactIds]),
    };

    this.beliefs.set(beliefId, record);
    this.chain.push(contentHash);
    this.hashToId.set(contentHash, beliefId);

    return record;
  }

  get(beliefId: string): BeliefRecord | null {
    return this.beliefs.get(beliefId) ?? null;
  }

  getByHash(contentHash: string): BeliefRecord | null {
    const id = this.hashToId.get(contentHash);
    return id ? this.beliefs.get(id) ?? null : null;
  }

  verifyChain(): boolean {
    for (let i = 0; i < this.chain.length; i += 1) {
      const contentHash = this.chain[i]!;
      const beliefId = this.hashToId.get(contentHash);
      if (!beliefId) return false;
      const record = this.beliefs.get(beliefId);
      if (!record) return false;
      if (hashContent(record.content) !== contentHash) return false;
      const expectedParent = i > 0 ? this.chain[i - 1]! : null;
      if (record.parentHash !== expectedParent) return false;
    }
    return true;
  }

  listAll(): BeliefRecord[] {
    const out: BeliefRecord[] = [];
    for (const h of this.chain) {
      const id = this.hashToId.get(h);
      if (id) {
        const r = this.beliefs.get(id);
        if (r) out.push(r);
      }
    }
    return out;
  }

  get size(): number {
    return this.beliefs.size;
  }
}
