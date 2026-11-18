import * as fs from 'fs';
import * as path from 'path';
import { describe, expect, it, vi } from 'vitest';

import { ExecFn, RewindCli } from '../src/cli';
import { loadSessionNodes, loadStepNodes, toSessionNodes, toStepNodes } from '../src/timelineModel';
import { SessionsResult, SummaryResult } from '../src/types';

function load<T>(name: string): T {
  return JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8')) as T;
}

function fixtureText(name: string): string {
  return fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8');
}

function cliReturning(stdout: string, code: number): RewindCli {
  const exec: ExecFn = async () => ({ stdout, stderr: '', code });
  return new RewindCli({ cliPath: 'rewindagents', exec });
}

describe('timelineModel', () => {
  it('lists sessions with their step counts (TreeView root)', () => {
    const sessions = load<SessionsResult>('sessions.json');

    const nodes = toSessionNodes(sessions.sessions);

    expect(nodes).toHaveLength(2);
    expect(nodes[0].kind).toBe('session');
    expect(nodes[0].label).toBe('2026-11-17-abcd1234');
    expect(nodes[0].description).toContain('3 steps');
  });

  it('lists steps with sequence, tool and files touched', () => {
    const summary = load<SummaryResult>('summary.json');

    const nodes = toStepNodes(summary.session, summary.steps);

    expect(nodes).toHaveLength(3);
    expect(nodes[1].label).toBe('2  Edit');
    expect(nodes[1].files).toEqual(['src/app.py', 'README.md']);
    expect(nodes[2].description).toBe('(no files)');
  });
});

describe('loadSessionNodes / loadStepNodes (CLI-backed, error-payload handling)', () => {
  it('loadSessionNodes returns tree nodes straight from a clean sessions() result', async () => {
    const cli = cliReturning(fixtureText('sessions.json'), 0);
    const showError = vi.fn();

    const nodes = await loadSessionNodes(cli, showError);

    expect(nodes).toHaveLength(2);
    expect(showError).not.toHaveBeenCalled();
  });

  it('loadSessionNodes catches a rewindagents-error payload, reports it, returns an empty list', async () => {
    const cli = cliReturning(fixtureText('error.json'), 1);
    const showError = vi.fn();

    const nodes = await loadSessionNodes(cli, showError);

    expect(nodes).toEqual([]);
    expect(showError).toHaveBeenCalledTimes(1);
    expect(showError.mock.calls[0][0]).toContain('step 99 is out of range');
  });

  it('loadStepNodes returns tree nodes straight from a clean summary() result', async () => {
    const cli = cliReturning(fixtureText('summary.json'), 0);
    const showError = vi.fn();

    const nodes = await loadStepNodes(cli, '2026-11-17-abcd1234', showError);

    expect(nodes).toHaveLength(3);
    expect(showError).not.toHaveBeenCalled();
  });

  it('loadStepNodes catches a rewindagents-error payload, reports it, returns an empty list', async () => {
    const cli = cliReturning(fixtureText('error.json'), 2);
    const showError = vi.fn();

    const nodes = await loadStepNodes(cli, '2026-11-17-abcd1234', showError);

    expect(nodes).toEqual([]);
    expect(showError).toHaveBeenCalledTimes(1);
    expect(showError.mock.calls[0][0]).toContain('step 99 is out of range');
  });
});
