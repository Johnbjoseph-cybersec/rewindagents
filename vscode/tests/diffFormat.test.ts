import * as fs from 'fs';
import * as path from 'path';
import { describe, expect, it } from 'vitest';

import { formatDiffDocument } from '../src/diffFormat';
import { DiffResult } from '../src/types';

function loadDiff(): DiffResult {
  return JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'diff.json'), 'utf8')) as DiffResult;
}

describe('formatDiffDocument', () => {
  it('renders every file when no path filter is given', () => {
    const text = formatDiffDocument(loadDiff());

    expect(text).toContain('src/app.py');
    expect(text).toContain('README.md');
    expect(text).toContain('print("bye")');
  });

  it('renders only the matching file when a path is given', () => {
    const text = formatDiffDocument(loadDiff(), 'src/app.py');

    expect(text).toContain('src/app.py');
    expect(text).not.toContain('README.md');
  });

  it('says plainly when nothing matches, instead of an empty document', () => {
    const text = formatDiffDocument(loadDiff(), 'nope.txt');

    expect(text).toContain('No changes recorded');
  });
});
