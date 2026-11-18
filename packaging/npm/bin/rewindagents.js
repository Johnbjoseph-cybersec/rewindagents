#!/usr/bin/env node
'use strict';

/*
 * rewindagents npm shim.
 *
 * This package has zero npm dependencies. Plain Node only: it locates a
 * python3 interpreter, creates a dedicated virtual environment under the
 * user's home directory the first time it runs, pip-installs the pinned
 * rewindagents release from PyPI into that venv once, then execs the venv's
 * own `rewindagents` console script, passing argv through untouched and
 * exiting with whatever code the real CLI returned.
 *
 * The real rewindagents CLI's exit-code contract (0 done, 1 partial/file
 * issue, 2 cannot run / usage) is defined by the Python package, not by this
 * shim; this file must not swallow or remap it.
 */

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const PKG_VERSION = require('../package.json').version;
const PACKAGE_SPEC = 'rewindagents==' + PKG_VERSION;
const MIN_PYTHON = [3, 10];

function fail(message) {
  process.stderr.write('rewindagents: ' + message + '\n');
  process.exit(2);
}

// Runs `python3 -c '...'`, which both prints the interpreter's (major, minor)
// version and exits 0 only when it is new enough. A single spawn covers the
// "locate python3 and check >=3.10" requirement without parsing free-form
// `--version` text.
function checkPython3() {
  const probe =
    'import sys; v = sys.version_info[:2]; print("%d.%d" % v); ' +
    'sys.exit(0 if v >= (' + MIN_PYTHON[0] + ", " + MIN_PYTHON[1] + ') else 1)';

  const result = spawnSync('python3', ['-c', probe], { encoding: 'utf8' });

  if (result.error) {
    if (result.error.code === 'ENOENT') {
      fail(
        'python3 was not found on PATH.\n' +
          'Install Python 3.10 or newer (https:' +
          '//www.python.org/downloads/) ' +
          'and make sure "python3" is on PATH, then run this command again.'
      );
    }
    fail('could not run python3 (' + result.error.message + ').');
  }

  const reported = (result.stdout || '').trim() || 'unknown';

  if (result.status !== 0) {
    fail(
      'found python3 (version ' +
        reported +
        '), but rewindagents needs Python ' +
        MIN_PYTHON.join('.') +
        ' or newer. Install a newer Python 3 and make sure it is the one ' +
        'on PATH as "python3".'
    );
  }
}

function venvDir() {
  return path.join(os.homedir(), '.rewindagents', 'npm', 'venv-' + PKG_VERSION);
}

function venvPythonBin(venv) {
  return process.platform === 'win32'
    ? path.join(venv, 'Scripts', 'python.exe')
    : path.join(venv, 'bin', 'python3');
}

function venvRewindagentsBin(venv) {
  return process.platform === 'win32'
    ? path.join(venv, 'Scripts', 'rewindagents.exe')
    : path.join(venv, 'bin', 'rewindagents');
}

// Creates the venv and pip-installs the pinned rewindagents release into it,
// but only the first time: if the venv's own `rewindagents` script already
// exists, this is a no-op, so a second run never reinstalls.
function ensureVenv(venv) {
  const rewindagentsBin = venvRewindagentsBin(venv);
  if (fs.existsSync(rewindagentsBin)) {
    return;
  }

  if (!fs.existsSync(venv)) {
    fs.mkdirSync(path.dirname(venv), { recursive: true });
    const create = spawnSync('python3', ['-m', 'venv', venv], { stdio: 'inherit' });
    if (create.error) {
      fail('failed to create a virtual environment at ' + venv + ' (' + create.error.message + ').');
    }
    if (create.status !== 0) {
      fail('failed to create a virtual environment at ' + venv + ' (exit code ' + create.status + ').');
    }
  }

  const pythonBin = venvPythonBin(venv);
  const install = spawnSync(
    pythonBin,
    ['-m', 'pip', 'install', '--quiet', '--disable-pip-version-check', PACKAGE_SPEC],
    { stdio: 'inherit' }
  );
  if (install.error) {
    fail('failed to install ' + PACKAGE_SPEC + ' into ' + venv + ' (' + install.error.message + ').');
  }
  if (install.status !== 0) {
    fail('failed to install ' + PACKAGE_SPEC + ' into ' + venv + ' (pip exit code ' + install.status + ').');
  }

  if (!fs.existsSync(rewindagentsBin)) {
    fail('install finished but ' + rewindagentsBin + ' was not found.');
  }
}

function main() {
  checkPython3();

  const venv = venvDir();
  ensureVenv(venv);

  const rewindagentsBin = venvRewindagentsBin(venv);
  const args = process.argv.slice(2);

  const child = spawn(rewindagentsBin, args, { stdio: 'inherit' });

  child.on('error', (err) => {
    fail('failed to run ' + rewindagentsBin + ' (' + err.message + ').');
  });

  child.on('exit', (code, signal) => {
    if (code === null) {
      // Killed by a signal rather than exiting normally: there is no 0/1/2
      // code to propagate, so report it as the "cannot run" case.
      process.stderr.write('rewindagents: child process terminated by signal ' + signal + '\n');
      process.exit(2);
    }
    process.exit(code);
  });
}

main();
