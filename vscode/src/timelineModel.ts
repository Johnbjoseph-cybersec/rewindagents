import { RewindCli, RewindCliError } from './cli';
import { SessionInfo, SummaryStep } from './types';

/**
 * Shows the user one message and returns, no answer expected. Same seam
 * shape as `rewindActions.ShowMessageFn` (kept as its own type here rather
 * than imported, so this module stays independent of `rewindActions`'s own
 * exports); the real extension wires both to
 * `vscode.window.showErrorMessage`.
 */
export type ShowMessageFn = (message: string) => void;

export interface SessionNode {
  kind: 'session';
  session: string;
  label: string;
  description: string;
}

export interface StepNode {
  kind: 'step';
  session: string;
  seq: number;
  label: string;
  description: string;
  files: string[];
}

export type RewindNode = SessionNode | StepNode;

/** Pure transform from a `sessions --json` result into tree nodes. */
export function toSessionNodes(sessions: SessionInfo[]): SessionNode[] {
  return sessions.map((s) => ({
    kind: 'session' as const,
    session: s.session,
    label: s.session,
    description: `${s.steps} step${s.steps === 1 ? '' : 's'} - ${s.first_ts} to ${s.last_ts}`,
  }));
}

/** Pure transform from a `summary --json` result into tree nodes. */
export function toStepNodes(session: string, steps: SummaryStep[]): StepNode[] {
  return steps.map((s) => ({
    kind: 'step' as const,
    session,
    seq: s.seq,
    label: `${s.seq}  ${s.tool}`,
    description: s.files.length ? s.files.join(', ') : '(no files)',
    files: s.files,
  }));
}

/**
 * Loads the TreeView's root (one node per session) straight from the CLI.
 * `cli.sessions()` throws `RewindCliError` when the CLI's own stdout is the
 * `rewindagents-error` shape (an unreadable or tampered log); that is
 * caught here and surfaced through `showError` instead of propagating as
 * an unhandled rejection out of a `TreeDataProvider.getChildren` call,
 * which VS Code has no useful way to display. An empty tree, not a crash,
 * is what the view shows on that path.
 */
export async function loadSessionNodes(cli: RewindCli, showError: ShowMessageFn): Promise<SessionNode[]> {
  try {
    const result = await cli.sessions();
    return toSessionNodes(result.sessions);
  } catch (e) {
    if (e instanceof RewindCliError) {
      showError(e.message);
      return [];
    }
    throw e;
  }
}

/**
 * Loads one session's steps (a TreeView session node's children) straight
 * from the CLI. Same `RewindCliError` handling as `loadSessionNodes` --
 * see its doc comment.
 */
export async function loadStepNodes(cli: RewindCli, session: string, showError: ShowMessageFn): Promise<StepNode[]> {
  try {
    const result = await cli.summary(session);
    return toStepNodes(session, result.steps);
  } catch (e) {
    if (e instanceof RewindCliError) {
      showError(e.message);
      return [];
    }
    throw e;
  }
}
