import type { AppendOnlyBeliefStore } from "../memory/appendOnlyStore.js";
import type { ArtifactStore } from "../storage/artifacts.js";

export function verifyArtifactIntegrity(store: ArtifactStore, contentHash: string): boolean {
  return store.verify(contentHash);
}

export function verifyBeliefChain(store: AppendOnlyBeliefStore): boolean {
  return store.verifyChain();
}

export function verifyAllArtifacts(
  store: ArtifactStore,
  hashes: readonly string[],
): Record<string, boolean> {
  const result: Record<string, boolean> = {};
  for (const h of hashes) result[h] = verifyArtifactIntegrity(store, h);
  return result;
}
