"""Negative controls for the in-browser FLAMeS unit tests: each mutation injects a realistic defect;
the vitest suite must FAIL for every one of them (otherwise the test is vacuous).

    python -I negative_controls.py <frontend dir> [--out results.json]

Every file is snapshotted before and restored in a `finally`, and the script verifies the SHA-256 of
every touched file after restoring. Do NOT run while anyone else edits these files.
"""
import argparse, hashlib, json, re, subprocess, sys, time
from pathlib import Path

TESTS = ['src/services/flames/__tests__/preprocess.test.ts', 'src/services/flames/__tests__/slidingWindow.test.ts',
         'src/services/flames/__tests__/axes-nifti.test.ts', 'src/services/flames/__tests__/pipeline.test.ts',
         'src/services/flames/__tests__/draft-model.test.ts']

MUTATIONS = [
    ('M1 Math.round instead of half-to-even (np.round)', 'src/services/flames/preprocess.ts',
     'export function roundHalfEven(x: number): number {\n', 'export function roundHalfEven(x: number): number {\n  return Math.round(x);\n'),
    ('M2 network spacing not permuted (sx, sy, sz)', 'src/services/flames/axes.ts',
     'return [spacing[0], spacing[2], spacing[1]];', 'return [spacing[0], spacing[1], spacing[2]];'),
    ('M3 nonzero mask without binary_fill_holes', 'src/services/flames/preprocess.ts',
     "for (let i = 0; i < n; i++) out[i] = state[i] === 2 ? 0 : 1;", "for (let i = 0; i < n; i++) out[i] = data[i] !== 0 ? 1 : 0;"),
    ('M4 network order (i, j, k) instead of transpose_forward (i, k, j)', 'src/services/flames/axes.ts',
     'for (let i = 0; i < nx; i++) out[(i * nz + k) * ny + j] = data[src + i];', 'for (let i = 0; i < nx; i++) out[(i * ny + j) * nz + k] = data[src + i];'),
    ('M5 no clipping to the input range after cubic resampling', 'src/services/flames/preprocess.ts',
     '    for (let i = 0; i < out.length; i++) out[i] = Math.min(Math.max(out[i], min), max);\n    return out;',
     '    for (let i = 0; i < out.length; i++) out[i] = out[i];\n    return out;'),
    ('M6 nearest neighbour along z rounds down (floor) instead of to nearest', 'src/services/flames/preprocess.ts',
     'out[o] = line[Math.min(Math.max(Math.floor(x + 0.5), 0), last)];', 'out[o] = line[Math.min(Math.max(Math.floor(x), 0), last)];'),
    ('M7 Gaussian sigma doubled', 'src/services/flames/slidingWindow.ts',
     'const sigma = n * sigmaScale;', 'const sigma = n * sigmaScale * 2;'),
    ('M8 mirrored predictions not flipped back', 'src/services/flames/slidingWindow.ts',
     'const back = axes.length ? flipAxes(logits, patch, axes, 2) : logits;', 'const back = logits;'),
    ('M9 draft grid gate compares rows with columns', 'src/services/flames/draft.ts',
     'if (rows !== height || columns !== width', 'if (rows !== width || columns !== height'),
    ('M10 app order = NIfTI order (RC-031 transpose dropped)', 'src/services/flames/axes.ts',
     'for (let i = 0; i < nx; i++) out[(k * nx + i) * ny + j] = data[src + i];', 'for (let i = 0; i < nx; i++) out[src + i] = data[src + i];'),
    ('M11 skull-strip border gate disabled', 'src/services/flames/pipeline.ts',
     'if (border > GATES.maxBorderNonzeroFraction) {', 'if (border > 1e9) {'),
    ('M12 model integrity check skipped', 'src/services/flames/modelStore.ts',
     '  if (digest !== asset.sha256) {', '  if (false && digest !== asset.sha256) {'),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('frontend', type=Path)
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    files = {f for _, f, _, _ in MUTATIONS}
    snapshot = {f: (a.frontend / f).read_bytes() for f in files}
    digests = {f: sha(a.frontend / f) for f in files}
    results = []
    npx = 'npx.cmd' if sys.platform == 'win32' else 'npx'
    try:
        for name, rel, old, new in MUTATIONS:
            path = a.frontend / rel
            text = snapshot[rel].decode('utf-8')
            assert text.count(old) == 1, f'{name}: anchor not found exactly once in {rel}'
            path.write_bytes(text.replace(old, new).encode('utf-8'))
            t = time.time()
            proc = subprocess.run([npx, 'vitest', 'run', *TESTS, '--pool=threads'], cwd=a.frontend,
                                  capture_output=True, text=True, encoding='utf-8', errors='replace')
            path.write_bytes(snapshot[rel])
            failed = proc.returncode != 0
            plain = re.sub(r'\x1b\[[0-9;]*m', '', proc.stdout)
            summary = [' '.join(l.split()) for l in plain.splitlines() if 'Tests' in l and ('failed' in l or 'passed' in l)]
            results.append({'mutation': name, 'detected': failed, 'summary': summary[-1] if summary else '',
                             'seconds': round(time.time() - t)})
            print(json.dumps(results[-1]), flush=True)
    finally:
        for rel, data in snapshot.items():
            (a.frontend / rel).write_bytes(data)
    restored = all(sha(a.frontend / f) == digests[f] for f in files)
    report = {'detected': sum(r['detected'] for r in results), 'total': len(results), 'restored_ok': restored,
              'results': results}
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}))
    if a.out:
        a.out.write_text(json.dumps(report, indent=1))
    sys.exit(0 if restored else 2)


if __name__ == '__main__':
    main()
