import { RewindCli, RewindCliError } from './cli';
import { RewindPlan } from './types';

/**
 * Asks the user to confirm a destructive action and resolves to whether
 * they agreed. In the real extension this wraps a VS Code modal warning
 * message; in tests it is a plain mock function, standing in for that
 * modal so the confirm-before-rewind flow can be exercised without
 * launching VS Code.
 */
export type ConfirmFn = (message: string) => Promise<boolean>;

/**
 * Shows the user one message and returns, no answer expected. In the real
 * extension this wraps `vscode.window.showErrorMessage`; in tests it is a
 * plain mock function, standing in for that so a `RewindCliError` can be
 * surfaced and asserted on without launching VS Code.
 */
export type ShowMessageFn = (message: string) => void;

export function planHasDrift(plan: RewindPlan): boolean {
  return Array.isArray(plan.drift) && plan.drift.length > 0;
}

export function formatRefusal(plan: RewindPlan): string {
  const header = `rewindagents refuses to rewind session ${plan.session} to step ${plan.to}: ` +
    `${plan.drift.length} file${plan.drift.length === 1 ? '' : 's'} changed after the steps it takes back.`;
  const lines = plan.drift.map((d) => `  ${d.path}: ${d.reason}`);
  return [header, ...lines].join('\n');
}

export function formatPlanSummary(plan: RewindPlan): string {
  const header = `Rewind plan for session ${plan.session} to step ${plan.to} ` +
    `(${plan.restores.length} file${plan.restores.length === 1 ? '' : 's'}):`;
  const lines = plan.restores.map((r) => `  ${r.action}  ${r.path}`);
  return [header, ...lines].join('\n');
}

export interface PreviewRewindResult {
  plan: RewindPlan;
  exitCode: number;
  refused: boolean;
  message: string;
}

/**
 * Runs `rewind N --dry-run --json` and renders a non-empty drift
 * array as a refusal notice. The dry run never changes anything on its
 * own, whatever the exit code.
 *
 * `rewindDryRun` throws `RewindCliError` when the CLI's own stdout is the
 * `rewindagents-error` shape (a step out of range, an ambiguous session, a
 * log that does not verify) -- that is caught here and surfaced through
 * `showError` instead of propagating as an unhandled rejection; the caller
 * gets `undefined` back rather than a value with no plan to render.
 */
export async function previewRewind(
  cli: RewindCli,
  to: number,
  session: string | undefined,
  showError: ShowMessageFn,
): Promise<PreviewRewindResult | undefined> {
  let plan: RewindPlan;
  let exitCode: number;
  try {
    ({ plan, exitCode } = await cli.rewindDryRun(to, session));
  } catch (e) {
    if (e instanceof RewindCliError) {
      showError(e.message);
      return undefined;
    }
    throw e;
  }
  const refused = planHasDrift(plan);
  return {
    plan,
    exitCode,
    refused,
    message: refused ? formatRefusal(plan) : formatPlanSummary(plan),
  };
}

export type ConfirmAndRewindOutcome =
  | { cancelled: true; ran: false }
  | { cancelled: false; ran: true; refused: boolean; message: string };

/**
 * Shows a confirmation first (via the injected `confirm` function), and
 * only then runs the real `rewind N`. Never passes a force option.
 * On exit 1 the rewind was refused and nothing changed; that is reported
 * as a refusal, never retried and never hidden.
 */
export async function confirmAndRewind(
  cli: RewindCli,
  to: number,
  session: string | undefined,
  confirm: ConfirmFn,
  confirmMessage = `Rewind session ${session ?? '(latest)'} to step ${to}? This changes files on disk.`,
): Promise<ConfirmAndRewindOutcome> {
  const confirmed = await confirm(confirmMessage);
  if (!confirmed) {
    return { cancelled: true, ran: false };
  }
  const result = await cli.rewind(to, session);
  const refused = result.code === 1;
  return {
    cancelled: false,
    ran: true,
    refused,
    message: refused ? result.stderr || result.stdout : result.stdout,
  };
}
