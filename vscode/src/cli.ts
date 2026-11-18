import { spawn } from 'child_process';

import {
  DiffResult,
  ErrorResult,
  ReplayResult,
  RewindPlan,
  SessionsResult,
  SummaryResult,
} from './types';

/**
 * Thrown by every `RewindCli` method that parses `--json` output when the CLI's own
 * stdout is the `rewindagents-error` shape (`src/rewindagents/jsonout.py`'s
 * `error_payload`): a step out of range, an ambiguous session, a log that does not
 * verify. `message` is the CLI's own `error` field, verbatim -- the same text a
 * human running the command without `--json` would read on stderr.
 */
export class RewindCliError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RewindCliError';
  }
}

export interface ExecResult {
  stdout: string;
  stderr: string;
  code: number;
}

/**
 * One process launch. Injectable so every test in this extension runs
 * against fixture JSON instead of a real rewindagents binary.
 */
export type ExecFn = (cliPath: string, args: string[], cwd: string | undefined) => Promise<ExecResult>;

export const spawnExec: ExecFn = (cliPath, args, cwd) =>
  new Promise((resolve, reject) => {
    const child = spawn(cliPath, args, { cwd });
    let stdout = '';
    let stderr = '';
    child.stdout?.on('data', (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr?.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on('error', reject);
    child.on('close', (code) => resolve({ stdout, stderr, code: code ?? 0 }));
  });

export interface RewindCliOptions {
  cliPath: string;
  cwd?: string;
  exec?: ExecFn;
}

/**
 * The only place in this extension that spawns the rewindagents binary.
 *
 * Every method below speaks exactly one of the frozen `--json` query
 * commands, or one of the two plain action commands (`rewind N`,
 * `revert N`, step positional per the real CLI's argparse, not a
 * `--to`/`--step` flag). Nothing here reads a `.rewindagents/` file, nothing
 * here parses human-format output, and nothing here reimplements diff,
 * hashing or log logic: everything comes from CLI stdout/exit code.
 *
 * No method ever appends a force option. A refusal (drift or conflict)
 * is reported as-is to the caller; it is never retried or swallowed.
 */
export class RewindCli {
  private readonly cliPath: string;
  private readonly cwd?: string;
  private readonly exec: ExecFn;

  constructor(options: RewindCliOptions) {
    this.cliPath = options.cliPath;
    this.cwd = options.cwd;
    this.exec = options.exec ?? spawnExec;
  }

  /** `rewindagents sessions --json` */
  async sessions(): Promise<SessionsResult> {
    const { stdout } = await this.run(['sessions', '--json']);
    return this.parseResult<SessionsResult>(stdout, 'rewindagents-sessions');
  }

  /** `rewindagents summary --json [--session S]` */
  async summary(session?: string): Promise<SummaryResult> {
    const args = ['summary', '--json'];
    if (session) {
      args.push('--session', session);
    }
    const { stdout } = await this.run(args);
    return this.parseResult<SummaryResult>(stdout, 'rewindagents-summary');
  }

  /** `rewindagents diff --json STEP [PATH...] [--session S]` */
  async diff(step: number, session?: string, paths: string[] = []): Promise<DiffResult> {
    const args = ['diff', '--json', String(step), ...paths];
    if (session) {
      args.push('--session', session);
    }
    const { stdout } = await this.run(args);
    return this.parseResult<DiffResult>(stdout, 'rewindagents-diff');
  }

  /** `rewindagents replay --json [--step N] [--session S]` */
  async replay(session?: string, step?: number): Promise<ReplayResult> {
    const args = ['replay', '--json'];
    if (step !== undefined) {
      args.push('--step', String(step));
    }
    if (session) {
      args.push('--session', session);
    }
    const { stdout } = await this.run(args);
    return this.parseResult<ReplayResult>(stdout, 'rewindagents-replay');
  }

  /**
   * `rewindagents rewind N --dry-run --json [--session S] [--only PATH]...`
   *
   * `step` is positional in the real CLI (`rw.add_argument("step", ...)` in
   * src/rewindagents/cli.py) -- there is no `--to` flag. Exit code is 0
   * when the plan's drift array is empty and 1 when it is not; the plan is
   * printed either way, so both the plan and the exit code are returned to
   * the caller.
   */
  async rewindDryRun(
    to: number,
    session?: string,
    only: string[] = [],
  ): Promise<{ plan: RewindPlan; exitCode: number }> {
    const args = ['rewind', String(to), '--dry-run', '--json'];
    if (session) {
      args.push('--session', session);
    }
    for (const path of only) {
      args.push('--only', path);
    }
    const { stdout, code } = await this.run(args);
    return { plan: this.parseResult<RewindPlan>(stdout, 'rewindagents-rewind-plan'), exitCode: code };
  }

  /**
   * `rewindagents rewind N [--session S] [--only PATH]...`
   *
   * `step` is positional, same as `rewindDryRun` above. Never passes a
   * force option. On exit 1 the rewind was refused and nothing changed;
   * the caller decides how to show that, this method only reports it.
   */
  async rewind(to: number, session?: string, only: string[] = []): Promise<ExecResult> {
    const args = ['rewind', String(to)];
    if (session) {
      args.push('--session', session);
    }
    for (const path of only) {
      args.push('--only', path);
    }
    return this.run(args);
  }

  /**
   * `rewindagents revert N [--session S]`
   *
   * `step` is positional in the real CLI (`rv.add_argument("step", ...)`)
   * -- there is no `--step` flag. On exit 1 the revert was refused (a
   * conflict) and nothing changed.
   */
  async revert(step: number, session?: string): Promise<ExecResult> {
    const args = ['revert', String(step)];
    if (session) {
      args.push('--session', session);
    }
    return this.run(args);
  }

  private run(args: string[]): Promise<ExecResult> {
    return this.exec(this.cliPath, args, this.cwd);
  }

  /**
   * The one place every `--json` command's stdout is turned into a typed
   * result. Every call site above routes through here, so the three
   * outcomes a parse can have are handled exactly once, not once per
   * method:
   *
   * 1. `format` is `'rewindagents-error'` (the CLI's own hard-failure
   *    shape, `jsonout.error_payload`) -- throws `RewindCliError` carrying
   *    the CLI's own `error` message verbatim, regardless of which command
   *    produced it.
   * 2. `format` matches `expectedFormat` -- returns the parsed object, typed.
   * 3. Anything else (a format this method did not ask for, a JSON value
   *    that is not an object, or stdout that is not JSON at all -- the
   *    CLI prints its one JSON object on stdout for every exit code these
   *    commands use, but a caller should never trust that blindly) --
   *    throws a plain `Error` naming the unexpected shape, never a crash
   *    on an undefined field further down the call chain.
   */
  private parseResult<T extends { format: string }>(stdout: string, expectedFormat: T['format']): T {
    let parsed: unknown;
    try {
      parsed = JSON.parse(stdout);
    } catch (e) {
      throw new Error(
        `rewindagents did not print the expected '${expectedFormat}' JSON on stdout: ` +
          `stdout was not valid JSON (${(e as Error).message})`,
      );
    }
    const format = parsed && typeof parsed === 'object' ? (parsed as { format?: unknown }).format : undefined;
    if (format === 'rewindagents-error') {
      throw new RewindCliError((parsed as ErrorResult).error);
    }
    if (format !== expectedFormat) {
      throw new Error(
        `rewindagents printed an unexpected JSON shape (format: ${JSON.stringify(format)}), ` +
          `expected '${expectedFormat}'`,
      );
    }
    return parsed as T;
  }
}
