import * as fs from 'fs';
import * as path from 'path';
import { describe, expect, it, vi } from 'vitest';

import { ExecFn, RewindCli } from '../src/cli';
import { confirmAndRewind, previewRewind } from '../src/rewindActions';

function fixture(name: string): string {
  return fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8');
}

function cliReturning(stdout: string, code: number, stderr = ''): RewindCli {
  const exec: ExecFn = async () => ({ stdout, stderr, code });
  return new RewindCli({ cliPath: 'rewindagents', exec });
}

const noop = (): void => {
  // unused in tests that do not expect an error
};

describe('previewRewind', () => {
  it('reports a clean plan as not refused', async () => {
    const cli = cliReturning(fixture('rewind-plan-clean.json'), 0);

    const result = await previewRewind(cli, 1, 's1', noop);

    expect(result).not.toBeUndefined();
    expect(result?.refused).toBe(false);
    expect(result?.message).toContain('Rewind plan');
    expect(result?.message).toContain('src/app.py');
  });

  it('renders a non-empty drift array as a refusal notice', async () => {
    const cli = cliReturning(fixture('rewind-plan-drift.json'), 1);

    const result = await previewRewind(cli, 1, 's1', noop);

    expect(result).not.toBeUndefined();
    expect(result?.refused).toBe(true);
    expect(result?.message).toContain('refuses');
    expect(result?.message).toContain('README.md');
    expect(result?.message).not.toContain('force');
  });

  it('catches a rewindagents-error payload and surfaces it via the injected showError seam, never throwing', async () => {
    const cli = cliReturning(fixture('error.json'), 2);
    const showError = vi.fn();

    const result = await previewRewind(cli, 99, 's1', showError);

    expect(result).toBeUndefined();
    expect(showError).toHaveBeenCalledTimes(1);
    expect(showError.mock.calls[0][0]).toContain('step 99 is out of range');
  });
});

describe('confirmAndRewind (confirm-before-rewind flow, modal mocked)', () => {
  it('never runs the rewind when the mocked modal is declined', async () => {
    const calls: string[][] = [];
    const exec: ExecFn = async (_cliPath, args) => {
      calls.push(args);
      return { stdout: '', stderr: '', code: 0 };
    };
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });
    const confirm = vi.fn(async () => false);

    const outcome = await confirmAndRewind(cli, 1, 's1', confirm);

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(calls).toHaveLength(0);
    expect(outcome.cancelled).toBe(true);
  });

  it('runs the real rewind only after the mocked modal confirms, never with force', async () => {
    const calls: string[][] = [];
    const exec: ExecFn = async (_cliPath, args) => {
      calls.push(args);
      return { stdout: 'session s1: rewind to step 1 of 3 (did change 2 files)', stderr: '', code: 0 };
    };
    const cli = new RewindCli({ cliPath: 'rewindagents', exec });
    const confirm = vi.fn(async () => true);

    const outcome = await confirmAndRewind(cli, 1, 's1', confirm);

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(calls[0]).toEqual(['rewind', '1', '--session', 's1']);
    expect(calls[0]).not.toContain('--force');
    expect(outcome.cancelled).toBe(false);
    if (!outcome.cancelled) {
      expect(outcome.refused).toBe(false);
    }
  });

  it('on exit 1 reports a refusal instead of treating the rewind as done', async () => {
    const cli = cliReturning('', 1, 'rewindagents: rewind refused, nothing changed: 1 file changed');
    const confirm = vi.fn(async () => true);

    const outcome = await confirmAndRewind(cli, 1, 's1', confirm);

    expect(outcome.cancelled).toBe(false);
    if (!outcome.cancelled) {
      expect(outcome.refused).toBe(true);
      expect(outcome.message).toContain('refused');
    }
  });
});
