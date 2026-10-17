#!/usr/bin/env node
/**
 * Negative controls for the viewer-v3 safety tests (CAPA-001 §5 practice): apply one
 * deliberate defect at a time, run the guarding test file, expect it to FAIL, restore.
 * Each file is snapshotted in memory and restored in a finally block, and a final
 * scan confirms no mutation marker survived. Do NOT run while someone else edits
 * these files.
 *
 * Usage (from frontend/): node ../scripts/viewer/negative_controls.mjs
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

const MUTATIONS = [
  {
    id: 'strides-transpose',
    file: 'src/volume/sliceGeometry.ts',
    from: 'rowStep: (view.rowFlip ? -1 : 1) * stride[view.row],\n    colStep: (view.colFlip ? -1 : 1) * stride[view.col],',
    to: 'rowStep: (view.rowFlip ? -1 : 1) * stride[view.col],\n    colStep: (view.colFlip ? -1 : 1) * stride[view.row], /*MUTATION*/',
    tests: ['src/volume/sliceGeometry.test.ts', 'src/volume/parity.test.ts'],
  },
  {
    id: 'lr-convention-flip',
    file: 'src/volume/sliceGeometry.ts',
    from: "const lrFlip = convention === 'neurological' ? lr.sign === -1 : lr.sign === 1;",
    to: "const lrFlip = convention === 'neurological' ? lr.sign === 1 : lr.sign === -1; /*MUTATION*/",
    tests: ['src/volume/sliceGeometry.test.ts'],
  },
  {
    id: 'drop-scl-slope',
    file: 'src/volume/nifti.ts',
    from: 'return vol.scaled ? v * vol.slope + vol.inter : v;',
    to: 'return v; /*MUTATION*/',
    tests: ['src/volume/parity.test.ts'],
  },
  {
    id: 'skip-big-endian-swap',
    file: 'src/volume/nifti.ts',
    from: 'if (!h.littleEndian) swapBytes(new Uint8Array(copy), dt.bytes);',
    to: '/*MUTATION*/',
    tests: ['src/volume/parity.test.ts'],
  },
  {
    id: 'orientation-no-row-exclusion',
    file: 'src/volume/orientation.ts',
    from: 'for (let c = 0; c < 3; c++) R[outAx][c] = 0; // remove that world axis',
    to: '/*MUTATION*/',
    tests: ['src/volume/parity.test.ts'],
  },
  {
    id: 'mask-gather-wrong-layout',
    file: 'src/volume/maskPlane.ts',
    from: 'const stride = grid.layout === \'kij\' ? strideKij : strideKji;',
    to: 'const stride = strideKij; /*MUTATION*/',
    tests: ['src/volume/maskPlane.test.ts'],
  },
  {
    id: 'mask-grid-accepts-anything',
    file: 'src/volume/maskPlane.ts',
    from: '  if (mask.depth !== dims[2]) return null;',
    to: '  /*MUTATION*/',
    tests: ['src/volume/maskPlane.test.ts'],
  },
  {
    id: 'agreement-ignores-grid',
    file: 'src/volume/clientVolume.ts',
    from: "if (server.rows != null && server.rows !== n0) problems.push(`rows ${server.rows} ≠ ${n0}`);",
    to: '/*MUTATION*/',
    tests: ['src/volume/parity.test.ts'],
  },
];

const results = [];
for (const m of MUTATIONS) {
  const path = resolve(m.file);
  const original = readFileSync(path, 'utf8');
  if (!original.includes(m.from)) {
    results.push({ id: m.id, status: 'NOT-APPLIED (anchor missing)' });
    continue;
  }
  try {
    writeFileSync(path, original.replace(m.from, m.to));
    let failed = false;
    try {
      execFileSync(process.execPath, ['node_modules/vitest/vitest.mjs', 'run', ...m.tests, '--pool=threads'], { stdio: 'pipe' });
    } catch {
      failed = true;
    }
    results.push({ id: m.id, status: failed ? 'DETECTED (tests failed)' : 'MISSED (tests still pass)' });
  } finally {
    writeFileSync(path, original);
  }
}
for (const m of MUTATIONS) {
  if (readFileSync(resolve(m.file), 'utf8').includes('/*MUTATION*/')) {
    console.error(`!! mutation marker left in ${m.file}`);
    process.exitCode = 1;
  }
}
for (const r of results) console.log(`${r.id.padEnd(32)} ${r.status}`);
if (results.some((r) => !r.status.startsWith('DETECTED'))) process.exitCode = 1;
