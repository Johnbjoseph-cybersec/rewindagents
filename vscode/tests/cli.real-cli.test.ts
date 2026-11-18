import { execFileSync, spawn } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ExecResult, ExecFn, RewindCli, RewindCliError } from '../src/cli';

// vscode/tests -> vscode -> repo root -> src. This is the one test file in the extension
// that does NOT mock `exec`: it spawns the actual rewindagents CLI from this repo's own
// source (via PYTHONPATH, not any installed/stale copy -- see below) and checks the exact
// argv RewindCli builds against the real argparse contract in src/rewindagents/cli.py.
//
// Every other test in this suite injects a fake `exec` and would stay green even if the
// real CLI's flags changed under it -- that is exactly how the extension shipped
// `rewind --to N` / `revert --step N` while the real CLI only ever accepted a positional
// step (`rewind N` / `revert N`): npm test was green, and the exact production argv failed
// the real binary with exit 2 ("unrecognized arguments"). This file closes that gap.
const REPO_SRC = path.resolve(__dirname, '..', '..', 'src');

function findPython(): string | null {
  for (const candidate of ['python3', 'python']) {
    try {
      execFileSync(candidate, ['--version'], { stdio: 'ignore' });
      return candidate;
    } catch {
      // try the next candidate
    }
  }
  return null;
}

const PYTHON = findPython();
const CLI_SOURCE_PRESENT = fs.existsSync(path.join(REPO_SRC, 'rewindagents', 'cli.py'));
const CAN_RUN_REAL_CLI = PYTHON !== null && CLI_SOURCE_PRESENT;

/**
 * Spawns `python3 -m rewindagents <args>` against THIS repo's src/rewindagents, by putting
 * REPO_SRC first on PYTHONPATH. PYTHONPATH is searched before site-packages, so this is the
 * repo's current source even when an older `rewindagents` is pip-installed in whatever
 * environment the test runs in (verified by hand: activating this repo's own .venv, whose
 * site-packages holds a stale pre-positional-args copy, still resolves `import rewindagents`
 * to REPO_SRC once PYTHONPATH is set -- the installed copy is never reached).
 */
const realExec: ExecFn = (_cliPath, args, cwd) =>
  new Promise<ExecResult>((resolve, reject) => {
    const child = spawn(PYTHON as string, ['-m', 'rewindagents', ...args], {
      cwd,
      env: { ...process.env, PYTHONPATH: REPO_SRC },
    });
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

/** Writes one file and appends one log record for it, so `rewind`/`revert` have a log to act on. */
function recordOneStep(cwd: string): void {
  fs.writeFileSync(path.join(cwd, 'a.txt'), 'x\n');
  execFileSync(PYTHON as string, ['-m', 'rewindagents', 'record', '--session', 't1'], {
    cwd,
    env: { ...process.env, PYTHONPATH: REPO_SRC },
    input: JSON.stringify({ tool: 'write', args: { path: 'a.txt' }, result: 'ok' }),
  });
}

describe.skipIf(!CAN_RUN_REAL_CLI)(
  'RewindCli against the real rewindagents CLI (python3 -m rewindagents, exec not mocked)',
  () => {
    let dir: string;

    beforeEach(() => {
      dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rewindagents-vscode-it-'));
      recordOneStep(dir);
    });

    afterEach(() => {
      fs.rmSync(dir, { recursive: true, force: true });
    });

    it('rewindDryRun() sends an argv the real binary accepts, and returns the frozen plan shape', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });

      const { plan, exitCode } = await cli.rewindDryRun(0, 't1');

      expect(exitCode).toBe(0);
      expect(plan.format).toBe('rewindagents-rewind-plan');
      expect(plan.session).toBe('t1');
      expect(plan.to).toBe(0);
      expect(plan.drift).toEqual([]);
    });

    it('rewind() sends an argv the real binary accepts (step is positional, no --to flag)', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });

      const result = await cli.rewind(0, 't1');

      expect(result.code).toBe(0);
      expect(result.stderr).not.toContain('unrecognized arguments');
    });

    it('revert() sends an argv the real binary accepts (step is positional, no --step flag)', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });

      const result = await cli.revert(1, 't1');

      // This fixture's one record has no tracked file checkpoint, so the real CLI refuses
      // with a domain-level RewindError ("nothing to revert", exit 1) -- a legitimate
      // business-logic refusal. The one thing this test exists to rule out is the usage
      // error (exit 2, "unrecognized arguments: --step") that the old --step flag produced
      // against this same real binary (see the regression-control test below).
      expect(result.code).not.toBe(2);
      const output = result.stdout + result.stderr;
      expect(output).not.toContain('unrecognized arguments');
    });

    it('regression control: the old --to/--step argv really did fail the real binary with exit 2', async () => {
      // Proves the three tests above are a meaningful probe, not a vacuous one: the exact
      // argv the extension used to send (--to N / --step N) is rejected by this same real
      // binary with exit 2, "unrecognized arguments". If a future change to cli.ts
      // reintroduces --to/--step, the tests above fail the same way this one currently
      // passes.
      const brokenRewind = await realExec('unused', ['rewind', '--to', '0', '--dry-run', '--json', '--session', 't1'], dir);
      expect(brokenRewind.code).toBe(2);
      expect(brokenRewind.stderr).toContain('unrecognized arguments');

      const brokenRevert = await realExec('unused', ['revert', '--step', '1', '--session', 't1'], dir);
      expect(brokenRevert.code).toBe(2);
      expect(brokenRevert.stderr).toContain('unrecognized arguments');
    });
  },
);

/**
 * A claude-shaped PreToolUse/PostToolUse hook payload, per `tests/test_hook.py`'s own `payload()`
 * fixture in the Python suite (`session_id`, `cwd`, `hook_event_name`, `tool_name`, `tool_input`,
 * and `tool_response` when there is one) -- the shape `agents.normalize` expects for the default
 * agent (`agents.DEFAULT == "claude"`).
 */
function hookPayload(
  cwd: string,
  event: 'PreToolUse' | 'PostToolUse',
  tool: string,
  toolInput: Record<string, unknown>,
  response?: unknown,
  session = 't1',
): Record<string, unknown> {
  const p: Record<string, unknown> = { session_id: session, cwd, hook_event_name: event, tool_name: tool, tool_input: toolInput };
  if (response !== undefined) {
    p.tool_response = response;
  }
  return p;
}

/** Runs `python3 -m rewindagents hook` once, feeding it one payload on stdin -- the real entry
 * point an agent's own hook runner calls, not a direct call into `hook.handle`. */
function runHook(payloadObj: Record<string, unknown>, cwd: string): void {
  execFileSync(PYTHON as string, ['-m', 'rewindagents', 'hook'], {
    cwd,
    env: { ...process.env, PYTHONPATH: REPO_SRC },
    input: JSON.stringify(payloadObj),
  });
}

/**
 * Records one real, checkpointed step on `app.py`: a `PreToolUse` hook call (which copies the
 * file's current bytes, or notes it is absent, into `.rewindagents/objects/`) around actually
 * writing `content`, then a `PostToolUse` call (which records the file's hash right after).
 *
 * This is deliberately NOT the plain `record` command the other describe block above uses --
 * `record` only appends a log line with whatever `args` a caller hands it, with no checkpoint of
 * its own, so a step written that way has nothing for `rewind`/`revert` to actually restore (see
 * that block's own `recordOneStep`, used only to prove the CLI's argv shape). Driving the real
 * `hook` command instead, with this exact payload shape, is what turns "the JSON parses" into
 * "rewinding this step changes real bytes on disk" -- the thing this describe block exists to
 * prove end to end.
 */
function writeStepViaHook(cwd: string, content: string, session = 't1'): void {
  runHook(hookPayload(cwd, 'PreToolUse', 'Write', { file_path: 'app.py' }, undefined, session), cwd);
  fs.writeFileSync(path.join(cwd, 'app.py'), content);
  runHook(hookPayload(cwd, 'PostToolUse', 'Write', { file_path: 'app.py' }, { ok: true }, session), cwd);
}

describe.skipIf(!CAN_RUN_REAL_CLI)(
  'RewindCli end to end against the real CLI: a real recorded session, driven through sessions/summary/diff/replay/rewindDryRun/rewind/revert',
  () => {
    let dir: string;

    beforeEach(() => {
      dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rewindagents-vscode-e2e-'));
      // Two real, hook-checkpointed steps in one session: app.py absent -> "v1\n" -> "v2\n".
      // Verified by hand (see the campaign evidence file) that this reproduces, outside any test
      // harness, exactly what `python3 -m rewindagents sessions --json` etc. report below.
      writeStepViaHook(dir, 'v1\n');
      writeStepViaHook(dir, 'v2\n');
    });

    afterEach(() => {
      fs.rmSync(dir, { recursive: true, force: true });
    });

    it('sessions() lists the recorded session with its real step count', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });

      const result = await cli.sessions();

      expect(result.format).toBe('rewindagents-sessions');
      const session = result.sessions.find((s) => s.session === 't1');
      expect(session).toBeDefined();
      expect(session?.steps).toBe(2);
    });

    it('summary() lists both real steps, each touching app.py', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });

      const result = await cli.summary('t1');

      expect(result.format).toBe('rewindagents-summary');
      expect(result.steps).toHaveLength(2);
      expect(result.steps.every((s) => s.files.includes('app.py'))).toBe(true);
    });

    it('diff(1) shows the real, unified-diff change that rewinding to step 1 would make (app.py back to v1)', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });

      const result = await cli.diff(1, 't1');

      expect(result.format).toBe('rewindagents-diff');
      expect(result.files).toHaveLength(1);
      expect(result.files[0].path).toBe('app.py');
      expect(result.files[0].change).toBe('modified');
      expect(result.files[0].unified).toContain('-v2');
      expect(result.files[0].unified).toContain('+v1');
    });

    it('replay() lists each real step together with its own recorded result', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });

      const result = await cli.replay('t1');

      expect(result.format).toBe('rewindagents-replay');
      expect(result.steps).toHaveLength(2);
      expect(result.steps.every((s) => s.result.includes('"ok": true'))).toBe(true);
    });

    it('rewindDryRun(1) parses a real rewindagents-rewind-plan and changes nothing on disk', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });
      const before = fs.readFileSync(path.join(dir, 'app.py'), 'utf8');

      const { plan, exitCode } = await cli.rewindDryRun(1, 't1');

      expect(plan.format).toBe('rewindagents-rewind-plan');
      expect(plan.to).toBe(1);
      expect(plan.drift).toEqual([]);
      expect(plan.restores).toEqual([{ path: 'app.py', action: 'restore' }]);
      expect(exitCode).toBe(0);
      // a dry run is read-only, whatever the plan says it would do
      expect(fs.readFileSync(path.join(dir, 'app.py'), 'utf8')).toBe(before);
    });

    it('rewind(1) actually restores app.py to its step-1 bytes on disk, not just in the printed plan', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });
      expect(fs.readFileSync(path.join(dir, 'app.py'), 'utf8')).toBe('v2\n');

      const result = await cli.rewind(1, 't1');

      expect(result.code).toBe(0);
      expect(fs.readFileSync(path.join(dir, 'app.py'), 'utf8')).toBe('v1\n');
    });

    it(
      'drift: a hand edit made outside any recorded step makes the real CLI refuse -- ' +
        'rewindDryRun(1) reports exit 1 with a non-empty drift array, and rewind(1) leaves the ' +
        'hand edit on disk untouched (never passing --force; cli.ts has no force parameter at all)',
      async () => {
        const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });
        const handEdit = 'hand-edited, never through a hook\n';
        fs.writeFileSync(path.join(dir, 'app.py'), handEdit);

        const { plan, exitCode } = await cli.rewindDryRun(1, 't1');

        expect(exitCode).toBe(1);
        expect(plan.drift.length).toBeGreaterThan(0);
        expect(plan.drift[0].path).toBe('app.py');
        // the dry run itself never writes, drift or not
        expect(fs.readFileSync(path.join(dir, 'app.py'), 'utf8')).toBe(handEdit);

        const result = await cli.rewind(1, 't1');

        expect(result.code).toBe(1);
        const refusalText = (result.stdout + result.stderr).toLowerCase();
        expect(refusalText).toContain('refused');
        // the refusal is real: the hand edit this test exists to protect is still there
        expect(fs.readFileSync(path.join(dir, 'app.py'), 'utf8')).toBe(handEdit);
      },
    );

    it('an out-of-range step on diff() throws RewindCliError carrying the real CLI message verbatim', async () => {
      const cli = new RewindCli({ cliPath: 'unused-in-this-test', cwd: dir, exec: realExec });

      await expect(cli.diff(99, 't1')).rejects.toBeInstanceOf(RewindCliError);
      await expect(cli.diff(99, 't1')).rejects.toThrow(/step 99 is out of range/);
      // the real CLI's own exit code for this failure (StepRangeError from _diff_json) is 2, not 1
      const raw = await realExec('unused', ['diff', '--json', '99', '--session', 't1'], dir);
      expect(raw.code).toBe(2);
      expect(JSON.parse(raw.stdout)).toEqual({
        format: 'rewindagents-error',
        version: 1,
        error: expect.stringContaining('step 99 is out of range'),
      });
    });
  },
);
