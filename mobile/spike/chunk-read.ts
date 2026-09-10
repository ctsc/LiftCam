/**
 * Phase 2 upload spike: timed byte-range reads of a local video.
 * Throwaway — deleted in Phase 8. Do not import from mobile/src product code.
 */

import { File } from "expo-file-system";

export type PartSizeMb = 8 | 16;

export type PartTiming = {
  index: number;
  offset: number;
  bytesRead: number;
  ms: number;
};

export type ChunkReadResult = {
  uri: string;
  partSizeBytes: number;
  fileSizeBytes: number;
  partCount: number;
  totalMs: number;
  peakPartBytes: number;
  parts: PartTiming[];
  error?: string;
};

export async function runChunkRead(uri: string, partSizeMb: PartSizeMb): Promise<ChunkReadResult> {
  const partSizeBytes = partSizeMb * 1024 * 1024;
  const file = new File(uri);
  if (!file.exists) {
    return {
      uri,
      partSizeBytes,
      fileSizeBytes: 0,
      partCount: 0,
      totalMs: 0,
      peakPartBytes: 0,
      parts: [],
      error: "file does not exist",
    };
  }

  const fileSizeBytes = file.size;
  const parts: PartTiming[] = [];
  let peakPartBytes = 0;
  const t0 = Date.now();
  let handle: ReturnType<File["open"]> | null = null;

  try {
    handle = file.open();
    let offset = 0;
    let index = 0;
    while (offset < fileSizeBytes) {
      handle.offset = offset;
      const want = Math.min(partSizeBytes, fileSizeBytes - offset);
      const started = Date.now();
      const bytes = handle.readBytes(want);
      const ms = Date.now() - started;
      peakPartBytes = Math.max(peakPartBytes, bytes.byteLength);
      parts.push({ index, offset, bytesRead: bytes.byteLength, ms });
      offset += bytes.byteLength;
      index += 1;
      if (bytes.byteLength === 0) {
        break;
      }
    }
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return {
      uri,
      partSizeBytes,
      fileSizeBytes,
      partCount: parts.length,
      totalMs: Date.now() - t0,
      peakPartBytes,
      parts,
      error: message,
    };
  } finally {
    handle?.close();
  }

  return {
    uri,
    partSizeBytes,
    fileSizeBytes,
    partCount: parts.length,
    totalMs: Date.now() - t0,
    peakPartBytes,
    parts,
  };
}

export function formatChunkResult(result: ChunkReadResult): string {
  const lines = [
    `uri: ${result.uri}`,
    `file_size_mb: ${(result.fileSizeBytes / (1024 * 1024)).toFixed(2)}`,
    `part_size_mb: ${result.partSizeBytes / (1024 * 1024)}`,
    `part_count: ${result.partCount}`,
    `total_ms: ${result.totalMs}`,
    `peak_part_bytes: ${result.peakPartBytes}`,
  ];
  if (result.error) {
    lines.push(`error: ${result.error}`);
  }
  for (const p of result.parts) {
    lines.push(`part ${p.index}: offset=${p.offset} bytes=${p.bytesRead} ms=${p.ms}`);
  }
  return lines.join("\n");
}
