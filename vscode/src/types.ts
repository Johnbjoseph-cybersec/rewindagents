/**
 * The five frozen --json shapes the rewindagents CLI prints, plus the
 * action-command result types. These mirror the contract exactly; nothing
 * here is inferred from .rewindagents/ on disk, only from CLI stdout.
 */

export interface SessionInfo {
  session: string;
  steps: number;
  first_ts: string;
  last_ts: string;
}

export interface SessionsResult {
  format: 'rewindagents-sessions';
  version: number;
  sessions: SessionInfo[];
}

export interface SummaryStep {
  seq: number;
  ts: string;
  actor: string;
  event: string;
  tool: string;
  files: string[];
}

export interface SummaryResult {
  format: 'rewindagents-summary';
  version: number;
  session: string;
  steps: SummaryStep[];
}

export type DiffChange = 'created' | 'modified' | 'deleted';

export interface DiffFileEntry {
  path: string;
  change: DiffChange;
  unified: string;
}

export interface DiffResult {
  format: 'rewindagents-diff';
  version: number;
  session: string;
  step: number;
  files: DiffFileEntry[];
}

export interface ReplayStep extends SummaryStep {
  result: string;
}

export interface ReplayResult {
  format: 'rewindagents-replay';
  version: number;
  session: string;
  steps: ReplayStep[];
}

export type RestoreAction = 'restore' | 'delete' | 'create';

export interface RewindRestore {
  path: string;
  action: RestoreAction;
}

export interface RewindDrift {
  path: string;
  reason: string;
}

export interface RewindPlan {
  format: 'rewindagents-rewind-plan';
  version: number;
  session: string;
  to: number;
  restores: RewindRestore[];
  drift: RewindDrift[];
}

/**
 * The one shape a hard failure takes on stdout under `--json`
 * (`src/rewindagents/jsonout.py`'s `error_payload`): a step out of range, an
 * ambiguous session, a log that does not verify. Still exactly one JSON
 * object, same as every success shape above -- `format` is the
 * discriminator a caller checks before trusting any other field.
 */
export interface ErrorResult {
  format: 'rewindagents-error';
  version: number;
  error: string;
}

/** Every shape the CLI's `--json` commands can print on stdout. */
export type AnyJsonResult =
  | SessionsResult
  | SummaryResult
  | DiffResult
  | ReplayResult
  | RewindPlan
  | ErrorResult;
