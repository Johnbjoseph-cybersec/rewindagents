import { DiffResult } from './types';

/**
 * Turns a `diff --json` result into plain text for a readonly document.
 * Pure formatting only: the unified text itself comes verbatim from the
 * CLI, never recomputed here.
 */
export function formatDiffDocument(diff: DiffResult, path?: string): string {
  const files = path ? diff.files.filter((f) => f.path === path) : diff.files;
  if (files.length === 0) {
    const where = path ? ` for ${path}` : '';
    return `No changes recorded at step ${diff.step}${where}.`;
  }
  return files
    .map((f) => `--- ${f.change}: ${f.path} ---\n${f.unified}`)
    .join('\n\n');
}
