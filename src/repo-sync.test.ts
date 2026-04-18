import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { execFileSync } from 'child_process';

import { collectRepoPaths } from './repo-sync.js';
import { RegisteredGroup } from './types.js';

function makeRepo(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
  execFileSync('git', ['-C', dir, 'init', '--quiet']);
}

function groupWithMounts(
  mounts: Array<{ hostPath: string; containerPath: string }>,
): RegisteredGroup {
  return {
    name: 'test',
    folder: 'test',
    trigger: '@Test',
    added_at: '2026-01-01T00:00:00Z',
    containerConfig: {
      additionalMounts: mounts.map((m) => ({ ...m, readonly: false })),
    },
  };
}

describe('collectRepoPaths', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'repo-sync-test-'));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('returns empty array when no groups have mounts', () => {
    expect(collectRepoPaths({})).toEqual([]);
    expect(
      collectRepoPaths({ g: groupWithMounts([]) }),
    ).toEqual([]);
  });

  it('discovers a repo when the mount root is itself a git repo', () => {
    makeRepo(tmpDir);
    const repos = collectRepoPaths({
      g: groupWithMounts([{ hostPath: tmpDir, containerPath: 'r' }]),
    });
    expect(repos).toEqual([tmpDir]);
  });

  it('discovers repos nested under a parent mount (depth 1)', () => {
    const a = path.join(tmpDir, 'a');
    const b = path.join(tmpDir, 'b');
    makeRepo(a);
    makeRepo(b);
    const repos = collectRepoPaths({
      g: groupWithMounts([{ hostPath: tmpDir, containerPath: 'x' }]),
    });
    expect(repos.sort()).toEqual([a, b].sort());
  });

  it('stops descending once a git repo is found (ignores nested .git under a repo)', () => {
    const outer = path.join(tmpDir, 'outer');
    const inner = path.join(outer, 'nested-repo');
    makeRepo(outer);
    makeRepo(inner); // would be a submodule-like structure
    const repos = collectRepoPaths({
      g: groupWithMounts([{ hostPath: tmpDir, containerPath: 'x' }]),
    });
    // Only the outer should be reported; we stop at the first .git encountered.
    expect(repos).toEqual([outer]);
  });

  it('skips node_modules and other noise directories', () => {
    const repo = path.join(tmpDir, 'proj');
    makeRepo(repo);
    const noisy = path.join(tmpDir, 'node_modules', 'some-pkg');
    makeRepo(noisy);
    const repos = collectRepoPaths({
      g: groupWithMounts([{ hostPath: tmpDir, containerPath: 'x' }]),
    });
    expect(repos).toEqual([repo]);
  });

  it('respects maxDepth', () => {
    const deep = path.join(tmpDir, 'a', 'b', 'c', 'd', 'deep');
    makeRepo(deep);
    const repos = collectRepoPaths(
      { g: groupWithMounts([{ hostPath: tmpDir, containerPath: 'x' }]) },
      2,
    );
    expect(repos).toEqual([]);
  });

  it('deduplicates repos shared across multiple groups', () => {
    const repo = path.join(tmpDir, 'shared');
    makeRepo(repo);
    const repos = collectRepoPaths({
      g1: groupWithMounts([{ hostPath: tmpDir, containerPath: 'x' }]),
      g2: groupWithMounts([{ hostPath: tmpDir, containerPath: 'y' }]),
    });
    expect(repos).toEqual([repo]);
  });

  it('silently skips mount paths that do not exist', () => {
    const repos = collectRepoPaths({
      g: groupWithMounts([
        { hostPath: path.join(tmpDir, 'missing'), containerPath: 'x' },
      ]),
    });
    expect(repos).toEqual([]);
  });

  it('silently skips mount paths that are files, not directories', () => {
    const file = path.join(tmpDir, 'file.txt');
    fs.writeFileSync(file, 'hello');
    const repos = collectRepoPaths({
      g: groupWithMounts([{ hostPath: file, containerPath: 'x' }]),
    });
    expect(repos).toEqual([]);
  });

  it('ignores groups without additionalMounts', () => {
    const repo = path.join(tmpDir, 'r');
    makeRepo(repo);
    const g: RegisteredGroup = {
      name: 'no-mounts',
      folder: 'no-mounts',
      trigger: '@X',
      added_at: '2026-01-01T00:00:00Z',
    };
    expect(collectRepoPaths({ g })).toEqual([]);
  });
});
