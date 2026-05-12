import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { IntegrityError, NotFoundError } from "../domain/errors.js";
import { hashContent, verifyHash } from "../domain/ids.js";

/**
 * Local filesystem artifact store with sha256 content addressing.
 *
 * Layout: `{basePath}/{hash[:4]}/{hash}/content`
 * Companion metadata: `{basePath}/{hash[:4]}/{hash}/meta.txt`
 *
 * Write-once: rewriting an existing hash with the same bytes is a no-op;
 * if the on-disk bytes do not match the hash, an IntegrityError is raised.
 * Port of `ironroot.storage.artifacts.ArtifactStore`.
 */
export class ArtifactStore {
  readonly basePath: string;

  constructor(basePath: string) {
    this.basePath = basePath;
    mkdirSync(basePath, { recursive: true });
  }

  private artifactPath(contentHash: string): string {
    const prefix = contentHash.slice(0, 4);
    return join(this.basePath, prefix, contentHash, "content");
  }

  store(data: Uint8Array, artifactType = "blob"): string {
    const buf = Buffer.from(data);
    const contentHash = hashContent(buf);
    const path = this.artifactPath(contentHash);

    if (existsSync(path)) {
      const existing = readFileSync(path);
      if (!verifyHash(existing, contentHash)) {
        throw new IntegrityError(`existing artifact corrupted: ${contentHash}`);
      }
      return contentHash;
    }

    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, buf);
    writeFileSync(join(dirname(path), "meta.txt"), `type=${artifactType}\nhash=${contentHash}\n`);
    return contentHash;
  }

  retrieve(contentHash: string): Uint8Array {
    const path = this.artifactPath(contentHash);
    if (!existsSync(path)) {
      throw new NotFoundError("artifact", contentHash);
    }
    const data = readFileSync(path);
    if (!verifyHash(data, contentHash)) {
      throw new IntegrityError(`artifact integrity check failed: ${contentHash}`);
    }
    return new Uint8Array(data);
  }

  exists(contentHash: string): boolean {
    return existsSync(this.artifactPath(contentHash));
  }

  verify(contentHash: string): boolean {
    try {
      const path = this.artifactPath(contentHash);
      if (!existsSync(path)) return false;
      return verifyHash(readFileSync(path), contentHash);
    } catch {
      return false;
    }
  }

  delete(contentHash: string): boolean {
    const path = this.artifactPath(contentHash);
    if (!existsSync(path)) return false;
    rmSync(dirname(path), { recursive: true, force: true });
    return true;
  }
}
