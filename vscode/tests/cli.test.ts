import * as fs from 'fs';
import * as path from 'path';
import { describe, expect, it } from 'vitest';

import { ExecFn, RewindCli, RewindCliError } from '../src/cli';

function fixture(name: string): string {
  return fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8');
}

interface RecordedCall {
  cliPath: string;
  args: string[];
  cwd: string | undefined;
}

function fakeExec(stdout: string, code = 0): ExecFn & { calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  const fn = async (cliPath: string, args: string[], cwd: string | undefined) => {
    calls.push({ cliPath, args, cwd });
    return { stdout, stderr: '', code };
  };
  return Object.assign(fn, { calls });
}

describe('RewindCli', () => {
  it('parses the sessions --json shape and respects the configured cliPath', async () => {
    const exec = fakeExec(fixture('sessions.json'));
    const cli = new RewindCli({ cliPath: '/opt/bin/rewindagents', exec });

    const result = await cli.sessions();

    expect(result.format).toBe('rewindagents-sessions');
    expect(result.sessions).toHaveLength(2);
    expect(result.sessions[0].session).toBe('2026-11-17-abcd1234');
    expect(result.sessions[0].steps).toBe(3);
    expect(exec.calls[0].cliPath).toBe('/opt/bin/rewindagents');
    expect(exec.calls[0].args).toEqual(['sessions', '--json']);
  });

  it('parses the summary --json shape and passes --session through', async () => {
    const exec = fakeExec(fixture('summary.json'));
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });

    const result = await cli.summary('2026-11-17-abcd1234');

    expect(result.format).toBe('rewindagents-summary');
    expect(result.steps).toHaveLength(3);
    expect(result.steps[1].files).toEqual(['src/app.py', 'README.md']);
    expect(exec.calls[0].args).toEqual(['summary', '--json', '--session', '2026-11-17-abcd1234']);
  });

  it('parses the diff --json shape', async () => {
    const exec = fakeExec(fixture('diff.json'));
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });

    const result = await cli.diff(2, '2026-11-17-abcd1234');

    expect(result.format).toBe('rewindagents-diff');
    expect(result.step).toBe(2);
    expect(result.files).toHaveLength(2);
    expect(result.files[0].change).toBe('modified');
    expect(result.files[1].change).toBe('created');
    expect(exec.calls[0].args).toEqual(['diff', '--json', '2', '--session', '2026-11-17-abcd1234']);
  });

  it('parses the replay --json shape', async () => {
    const exec = fakeExec(fixture('replay.json'));
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });

    const result = await cli.replay('2026-11-17-abcd1234');

    expect(result.format).toBe('rewindagents-replay');
    expect(result.steps[0].result).toBe('ok');
    expect(exec.calls[0].args).toEqual(['replay', '--json', '--session', '2026-11-17-abcd1234']);
  });

  it('parses a clean rewind-plan: exit 0, empty drift', async () => {
    const exec = fakeExec(fixture('rewind-plan-clean.json'), 0);
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });

    const { plan, exitCode } = await cli.rewindDryRun(1, '2026-11-17-abcd1234');

    expect(plan.format).toBe('rewindagents-rewind-plan');
    expect(plan.drift).toEqual([]);
    expect(plan.restores).toHaveLength(2);
    expect(exitCode).toBe(0);
    expect(exec.calls[0].args).toEqual([
      'rewind', '1', '--dry-run', '--json', '--session', '2026-11-17-abcd1234',
    ]);
  });

  it('parses a drifted rewind-plan: exit 1, plan still present', async () => {
    const exec = fakeExec(fixture('rewind-plan-drift.json'), 1);
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });

    const { plan, exitCode } = await cli.rewindDryRun(1, '2026-11-17-abcd1234');

    expect(exitCode).toBe(1);
    expect(plan.drift).toHaveLength(1);
    expect(plan.drift[0].path).toBe('README.md');
    expect(plan.restores).toHaveLength(1);
  });

  it('speaks rewind N (positional step, no --to flag) with no force option, ever', async () => {
    const exec = fakeExec('', 0);
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });

    await cli.rewind(1, 's1');

    expect(exec.calls[0].args).toEqual(['rewind', '1', '--session', 's1']);
    expect(exec.calls[0].args).not.toContain('--force');
    expect(exec.calls[0].args).not.toContain('--to');
  });

  it('speaks revert N (positional step, no --step flag)', async () => {
    const exec = fakeExec('', 0);
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });

    await cli.revert(2, 's1');

    expect(exec.calls[0].args).toEqual(['revert', '2', '--session', 's1']);
    expect(exec.calls[0].args).not.toContain('--step');
  });
});

describe('RewindCli against the rewindagents-error payload (every JSON-parsing method)', () => {
  // src/rewindagents/jsonout.py's error_payload(): the one shape a hard failure (a step out of
  // range, an ambiguous session, a log that does not verify) takes on stdout under --json,
  // whatever command produced it and whatever exit code it used. Every method below must throw
  // a typed RewindCliError carrying the CLI's own message, not mis-cast the error object as its
  // expected success shape (that crash -- e.g. previewRewind reading `plan.restores.length` off
  // an object with no `restores` field -- is exactly the HIGH finding this suite closes).
  const ERROR_MESSAGE =
    "step 99 is out of range: session 2026-11-17-abcd1234 has 2 steps, so use 0-2 (0 = before the first step); " +
    '`replay` lists them';

  it('sessions() throws RewindCliError carrying the CLI error message', async () => {
    const cli = new RewindCli({ cliPath: 'rewindagents', exec: fakeExec(fixture('error.json'), 1) });

    await expect(cli.sessions()).rejects.toBeInstanceOf(RewindCliError);
    await expect(cli.sessions()).rejects.toThrow(ERROR_MESSAGE);
  });

  it('summary() throws RewindCliError carrying the CLI error message', async () => {
    const cli = new RewindCli({ cliPath: 'rewindagents', exec: fakeExec(fixture('error.json'), 1) });

    await expect(cli.summary('2026-11-17-abcd1234')).rejects.toBeInstanceOf(RewindCliError);
    await expect(cli.summary('2026-11-17-abcd1234')).rejects.toThrow(ERROR_MESSAGE);
  });

  it('diff() throws RewindCliError carrying the CLI error message', async () => {
    const cli = new RewindCli({ cliPath: 'rewindagents', exec: fakeExec(fixture('error.json'), 2) });

    await expect(cli.diff(99, '2026-11-17-abcd1234')).rejects.toBeInstanceOf(RewindCliError);
    await expect(cli.diff(99, '2026-11-17-abcd1234')).rejects.toThrow(ERROR_MESSAGE);
  });

  it('replay() throws RewindCliError carrying the CLI error message', async () => {
    const cli = new RewindCli({ cliPath: 'rewindagents', exec: fakeExec(fixture('error.json'), 2) });

    await expect(cli.replay('2026-11-17-abcd1234', 99)).rejects.toBeInstanceOf(RewindCliError);
    await expect(cli.replay('2026-11-17-abcd1234', 99)).rejects.toThrow(ERROR_MESSAGE);
  });

  it('rewindDryRun() throws RewindCliError carrying the CLI error message', async () => {
    const cli = new RewindCli({ cliPath: 'rewindagents', exec: fakeExec(fixture('error.json'), 2) });

    await expect(cli.rewindDryRun(99, '2026-11-17-abcd1234')).rejects.toBeInstanceOf(RewindCliError);
    await expect(cli.rewindDryRun(99, '2026-11-17-abcd1234')).rejects.toThrow(ERROR_MESSAGE);
  });

  it('throws a plain Error (not RewindCliError) naming the unexpected shape on a format mismatch', async () => {
    // sessions.json is a real, valid shape -- just not the one summary() asked for. This is the
    // third outcome parseResult must handle: neither the expected shape nor the error shape.
    const cli = new RewindCli({ cliPath: 'rewindagents', exec: fakeExec(fixture('sessions.json'), 0) });

    await expect(cli.summary('s1')).rejects.not.toBeInstanceOf(RewindCliError);
    await expect(cli.summary('s1')).rejects.toThrow(/unexpected JSON shape/);
  });

  it('throws a plain Error (not RewindCliError) when stdout is not JSON at all', async () => {
    const cli = new RewindCli({ cliPath: 'rewindagents', exec: fakeExec('not json', 2) });

    await expect(cli.sessions()).rejects.not.toBeInstanceOf(RewindCliError);
    await expect(cli.sessions()).rejects.toThrow(/did not print the expected/);
  });
});
