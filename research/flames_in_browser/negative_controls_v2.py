"""Negative controls + "before the fix" runs for the review fixes of CP-FLAMES-BROWSER-001 (2026-10-17).

Every mutation re-introduces one defect the adversarial review found (or removes one new control); the named
tests must FAIL. "BEFORE" entries restore whole files from the commit the review was made on (d81cb78) and
show that the new tests fail on the old code. Re-review 2 (2026-10-18) adds the controls P*, U*, E*, B6-B10 and
"BEFORE-R*" runs against the commit that re-review was made on (c838bb1). All files are snapshotted and restored,
and their SHA-256 is checked afterwards.

    python -I research/flames_in_browser/negative_controls_v2.py <repo root> --out <results.json> [--only PREFIX]
    python -I research/flames_in_browser/negative_controls_v2.py <repo root> --out x.json --check-anchors
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

FE = 'frontend/'
T_HANDOFF = [FE + 'src/hooks/useSegmentationData.flamesDraft.test.tsx']
T_CARD = [FE + 'src/components/BrowserFlamesCard.test.tsx']
T_MODEL_NEW = [FE + 'src/services/flames/__tests__/modelStore.test.ts']
T_MODEL_OLD = [FE + 'src/services/flames/__tests__/draft-model.test.ts']
T_GATES = [FE + 'src/services/flames/__tests__/inputGates.test.ts', FE + 'src/services/flames/__tests__/pipeline.test.ts']
T_CANCEL = [FE + 'src/hooks/useBrowserFlames.cancel.test.tsx']
T_BACKEND = ['backend/tests/unit/test_rc047_ai_draft_provenance.py']
T_BANNER = [FE + 'src/components/AiDraftBanner.test.tsx']
T_DRAFT = [FE + 'src/services/flames/__tests__/draft-model.test.ts']

SD = FE + 'src/hooks/useSegmentationData.ts'
CARD = FE + 'src/components/BrowserFlamesCard.tsx'
MS = FE + 'src/services/flames/modelStore.ts'
CG = FE + 'src/services/flames/contrastGate.ts'
PL = FE + 'src/services/flames/pipeline.ts'
UBF = FE + 'src/hooks/useBrowserFlames.ts'
DRAFT = FE + 'src/services/flames/draft.ts'
BANNER = FE + 'src/components/AiDraftBanner.tsx'
SVC = 'backend/app/services/segmentation_service.py'
ROUTE = 'backend/app/api/routes/segmentation.py'
SCHEMAS = 'backend/app/models/schemas.py'

MUTATIONS = [
    # point 2 — AI draft never autosaved, stored with provenance, never "manual"
    ('H1 save-on-unload saves AI drafts again', SD, 'if (!isAiSegmentation(currentSegmentation.metadata)) {', 'if (true) {', T_HANDOFF),
    ('H2 provenance not sent on Save', SD, '...(aiProvenance ? { ai_provenance: aiProvenance } : {}),', '', T_HANDOFF),
    ('H3 server echo of the provenance not checked', SD, 'if (aiProvenance && !provenanceRecorded(', 'if (false && !provenanceRecorded(', T_HANDOFF),
    ('H4 open draft recorded as manual', SD, "segmentation_type: aiProvenance ? 'automatic' : 'manual',", "segmentation_type: 'manual',", T_HANDOFF),
    # point 3 — never discard unsaved work
    ('H5 unsaved-work check removed (hook)', SD, 'if (unsavedWorkRef.current && !options.discardUnsavedWork) {', 'if (false) {', T_HANDOFF),
    ('H6 card always discards unsaved work', CARD, 'onClick={() => openDraft(false)}', 'onClick={() => openDraft(true)}', T_CARD),
    # point 1 — empty result explicit (REQ-FUNC-036)
    ('H7 empty result shown as a normal summary', CARD, '{empty ? (', '{false ? (', T_CARD),
    ('H8 empty draft opens without acknowledgement', CARD, 'disabled={!grid?.ok || (empty && !emptyAcknowledged)}', 'disabled={!grid?.ok}', T_CARD),
    # point 5 — licence notice reachable
    ('H9 licence panel removed', CARD, 'data-testid="browser-flames-licences"', 'data-testid="x" hidden', T_CARD),
    # cancel never touches the open segmentation
    ('H10 cancel does not stop the worker', UBF, '  const cancel = useCallback(() => {\n    terminate();', '  const cancel = useCallback(() => {', T_CANCEL),
    # point 4 — model SHA-256 on download AND from the browser cache
    ('I1 cache copy not re-verified', MS, '        await verifyModel(bytes, asset);\n        onProgress?.(1);', '        onProgress?.(1);', T_MODEL_NEW),
    ('I2 download not verified', MS, '  await verifyModel(bytes, asset);\n  if (cache) {', '  if (cache) {', T_MODEL_NEW),
    ('I1-old same defect against the PRE-FIX tests', MS, '        await verifyModel(bytes, asset);\n        onProgress?.(1);', '        onProgress?.(1);', T_MODEL_OLD),
    ('I2-old same defect against the PRE-FIX tests', MS, '  await verifyModel(bytes, asset);\n  if (cache) {', '  if (cache) {', T_MODEL_OLD),
    # point 1 — input gates
    ('G1 T1 rule disabled', CG, 'if (score > FLAIR_GATE.maxDeepOverCortex) {', 'if (false) {', T_GATES),
    ('G2 T2 rule disabled', CG, 'if (features.fracAbove1p6 > FLAIR_GATE.maxBrightFraction) {', 'if (false) {', T_GATES),
    ('G3 header evidence can approve', CG, "  if (header.verdict === 'contradicts') {", "  if (header.verdict === 'supports') return { ok: true, ...base };\n  if (header.verdict === 'contradicts') {", T_GATES),
    ('G4 header refusal ignored', CG, "  if (header.verdict === 'contradicts') {", '  if (false) {', T_GATES),
    ('G5 dark skull clue disabled', PL, 'features.darkFraction > GATES.maxHeadDarkFraction', 'features.darkFraction > 1e9', T_GATES),
    ('G5b scalp-fat rim clue disabled', PL, 'features.rimBrightFraction > GATES.maxRimBrightFraction', 'features.rimBrightFraction > 1e9', T_GATES),
    ('G6 no local normalisation (bias field not cancelled)', CG, 'inorm[v] = local > 0 ? data[v] / local : 0;', 'inorm[v] = data[v];', T_GATES),
    ('G7 contrast refusal not enforced in the pipeline', PL, 'if (opts.contrastGate !== false && !contrast.ok) reasons.push(', 'if (false) reasons.push(', T_GATES),
    ('G8 unmeasurable contrast accepted', CG, '  if (!measurable) {', '  if (false) {', T_GATES),
    ('G9 implausible output (lesions > 25 % of brain) returned', PL,
     'if (brainVoxels > 0 && summary.lesionVoxels / brainVoxels > GATES.maxLesionFractionOfBrain) {', 'if (false) {', T_GATES),
    ('F1 feature flag ON by default', FE + 'src/config/features.ts',
     "BROWSER_FLAMES: getFeatureFlag('ENABLE_BROWSER_FLAMES', false),", "BROWSER_FLAMES: getFeatureFlag('ENABLE_BROWSER_FLAMES', true),",
     [FE + 'src/config/features.flames.test.ts']),
    # backend (point 2)
    ('B1 client can store a pre-confirmed draft', SVC,
     '                "review_status": "unreviewed", "reviewed_by": None, "reviewed_at": None,\n'
     '                "reviewed_mask_sha256": None,\n                # RC-049: who confirmed',
     '                # RC-049: who confirmed', T_BACKEND),
    ('B2 AI draft not typed automatic', 'backend/app/services/segmentation_service.py',
     'segmentation_type="automatic" if provenance else None,', 'segmentation_type=None,', T_BACKEND),
    ('B3 create route drops the provenance', 'backend/app/api/routes/segmentation.py',
     'ai_provenance=request.ai_provenance,', 'ai_provenance=None,', T_BACKEND),
    ('B4 any role can confirm', 'backend/app/api/routes/segmentation.py',
     'if getattr(current_user, "role", None) != UserRole.RADIOLOGIST:', 'if False:', T_BACKEND),
    ('B5 manual work can be "confirmed"', 'backend/app/api/routes/segmentation.py', '    if provenance is None:', '    if False:', T_BACKEND),
    # re-review 2, point 2 — the confirmation is bound to the exact mask; any change resets it
    ('B6 persist does not enforce the review binding', SVC, '        self.enforce_review_binding(seg_data)\n', '', T_BACKEND),
    ('B7 mask upload does not reset the review', ROUTE,
     'review_reset = segmentation_service.enforce_review_binding(seg_data)', 'review_reset = False', T_BACKEND),
    ('B8 confirmation accepted for any mask', ROUTE, '    if reviewed != current:\n', '    if False:\n', T_BACKEND),
    ('B9 confirmation does not record which mask', ROUTE, '            "reviewed_mask_sha256": current,\n', '', T_BACKEND),
    ('B10 sequence confirmer not taken from the authenticated user', SVC,
     '"sequence_confirmed_by": created_by if ai_provenance.sequence_evidence == "clinician" else None,', '', T_BACKEND),
    ('U1 confirm button shown with unsaved corrections', BANNER, ') : unreviewed && hasUnsavedChanges ? (', ') : false ? (', T_BANNER),
    ('U2 confirmation not bound to the mask on screen', BANNER, 'confirmAiReview(segmentationId, digest)',
     'confirmAiReview(segmentationId, provenance.model_sha256)', T_BANNER),
    ('U3 no provenance refresh after saving corrections', SD, 'if (!serverSeg && currentSegmentation.metadata?.ai_provenance) {',
     'if (false) {', T_HANDOFF),
    ('U4 stale "confirmed" kept when the refresh fails', SD,
     "? { ...seg.metadata.ai_provenance, review_status: 'unreviewed', reviewed_by: null, reviewed_at: null, reviewed_mask_sha256: null }",
     '? seg.metadata.ai_provenance', T_HANDOFF),
    ('U5 unsaved flag not published to the banner', SD, 'useSegmentationStore.getState().setHasUnsavedMaskChanges(unsavedMask);',
     'useSegmentationStore.getState().setHasUnsavedMaskChanges(false);', T_HANDOFF),
    # re-review 2, point 3 — the server echo must be exact and unreviewed
    ('P1 echo with another model hash accepted', DRAFT, '    echoed.model_sha256 === sent.model_sha256 &&\n', '', T_DRAFT + T_HANDOFF),
    ('P2 echo already "confirmed" accepted', DRAFT,
     "    echoed.review_status === 'unreviewed' && !echoed.reviewed_by && !echoed.reviewed_at && !echoed.reviewed_mask_sha256;",
     '    true;', T_DRAFT + T_HANDOFF),
    # re-review 2, point 1 — positive evidence of the sequence, fail closed
    ('E1 positive evidence not required', CG,
     "opts.clinicianConfirmedFlair === true ? 'clinician' : headerProvesFlair(header) ? 'header' : undefined;",
     "opts.clinicianConfirmedFlair === true ? 'clinician' : 'header';", T_GATES),
    ('E2 grey-matter class rule (second T1 rule) disabled', CG, 'if (features.frac45to80 > FLAIR_GATE.maxGreyClassFraction) {',
     'if (false) {', T_GATES),
    ('E3 a "FLAIR" header label alone counts as proof', CG,
     "    header.verdict === 'supports' &&\n    header.inversionTimeMs !== undefined &&",
     "    header.verdict === 'supports' ||\n    header.inversionTimeMs !== undefined &&", T_GATES),
    ('E4 run allowed without the sequence confirmation', CARD, 'disabled={!flairFileId || !sequenceConfirmed}',
     'disabled={!flairFileId}', T_CARD),
    ('E5 hook always claims the clinician confirmed', UBF, 'clinicianConfirmedFlair: options.clinicianConfirmedFlair === true,',
     'clinicianConfirmedFlair: true,', T_CANCEL),
    ('E6 confirmation carried over to another file', CARD, 'useEffect(() => setSequenceConfirmed(false), [flairFileId]);', '', T_CARD),
]

BEFORE = [
    ('BEFORE-2/3 hand-off: useSegmentationData.ts + BrowserFlamesCard.tsx as reviewed (d81cb78)', 'd81cb78', [SD, CARD], T_HANDOFF + T_CARD),
    ('BEFORE-1 gates: pipeline.ts as reviewed (d81cb78) — T1 phantom', 'd81cb78', [PL], [FE + 'src/services/flames/__tests__/pipeline.test.ts']),
    # re-review 2 was made on c838bb1
    ('BEFORE-R1 FLAIR gate as re-reviewed (c838bb1): contrastGate.ts + pipeline.ts', 'c838bb1', [CG, PL], T_GATES),
    ('BEFORE-R2a review binding, frontend as re-reviewed (c838bb1): AiDraftBanner.tsx + useSegmentationData.ts', 'c838bb1',
     [BANNER, SD], T_BANNER + T_HANDOFF),
    ('BEFORE-R2b review binding, backend as re-reviewed (c838bb1): service + route + schemas', 'c838bb1', [SVC, ROUTE, SCHEMAS], T_BACKEND),
    ('BEFORE-R3 provenance echo as re-reviewed (c838bb1): draft.ts', 'c838bb1', [DRAFT], T_DRAFT),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(repo: Path, tests):
    if tests[0].startswith('backend/'):
        py = Path(r'C:\Users\Nicolas\medical-imaging-viewer\backend\venv\Scripts\python.exe')
        proc = subprocess.run([str(py), '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *[t[len('backend/'):] for t in tests]],
                              cwd=repo / 'backend', capture_output=True, text=True, encoding='utf-8', errors='replace')
        out = proc.stdout + proc.stderr
        failed = sorted(set(re.findall(r'FAILED (\S+)', out))) or sorted(set(re.findall(r'ERROR (\S+)', out)))
        summary = [l for l in out.splitlines() if re.search(r'\d+ (passed|failed)', l)]
    else:
        npx = 'npx.cmd' if sys.platform == 'win32' else 'npx'
        proc = subprocess.run([npx, 'vitest', 'run', *[t[len(FE):] for t in tests], '--pool=threads'], cwd=repo / 'frontend',
                              capture_output=True, text=True, encoding='utf-8', errors='replace')
        out = re.sub(r'\x1b\[[0-9;]*m', '', proc.stdout + proc.stderr)
        failed = sorted(set(m.strip() for m in re.findall(r'^\s*[×✗]\s+(.+?)(?:\s+\d+ms)?$', out, re.M)))
        summary = [' '.join(l.split()) for l in out.splitlines() if 'Tests' in l and ('failed' in l or 'passed' in l)]
    return proc.returncode != 0, failed, (summary[-1] if summary else '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--check-anchors', action='store_true', help='only assert that every anchor occurs exactly once')
    a = ap.parse_args()
    if a.check_anchors:
        bad = []
        for name, rel, old, _new, _tests in MUTATIONS:
            text = (a.repo / rel).read_bytes().decode('utf-8').replace('\r\n', '\n')
            if text.count(old) != 1:
                bad.append(f'{name}: {text.count(old)} in {rel}')
        print('\n'.join(bad) or f'all {len(MUTATIONS)} anchors unique')
        return
    files = {m[1] for m in MUTATIONS} | {f for _, _, fs, _ in BEFORE for f in fs}
    snap = {f: (a.repo / f).read_bytes() for f in files}
    digests = {f: sha(a.repo / f) for f in files}
    results = []
    try:
        for name, rel, old, new, tests in MUTATIONS:
            if a.only and not name.startswith(a.only):
                continue
            text = snap[rel].decode('utf-8')
            if '\r\n' in text:  # working copies may use CRLF (core.autocrlf)
                old, new = old.replace('\n', '\r\n'), new.replace('\n', '\r\n')
            assert text.count(old) == 1, f'{name}: anchor found {text.count(old)} times in {rel}'
            (a.repo / rel).write_bytes(text.replace(old, new).encode('utf-8'))
            t = time.time()
            detected, failed, summary = run(a.repo, tests)
            (a.repo / rel).write_bytes(snap[rel])
            results.append({'id': name.split()[0], 'mutation': name, 'file': rel, 'tests': tests, 'detected': detected,
                            'failing_tests': failed, 'summary': summary, 'seconds': round(time.time() - t)})
            print(json.dumps(results[-1]), flush=True)
        for name, commit, rels, tests in BEFORE:
            if a.only and not name.startswith(a.only):
                continue
            for rel in rels:
                old = subprocess.run(['git', 'show', f'{commit}:{rel}'], cwd=a.repo, capture_output=True, check=True).stdout
                (a.repo / rel).write_bytes(old)
            t = time.time()
            detected, failed, summary = run(a.repo, tests)
            for rel in rels:
                (a.repo / rel).write_bytes(snap[rel])
            results.append({'id': name.split()[0], 'mutation': name, 'commit': commit, 'files': rels, 'tests': tests, 'detected': detected,
                            'failing_tests': failed, 'summary': summary, 'seconds': round(time.time() - t)})
            print(json.dumps(results[-1]), flush=True)
    finally:
        for rel, data in snap.items():
            (a.repo / rel).write_bytes(data)
    restored = all(sha(a.repo / f) == digests[f] for f in files)
    report = {'date': time.strftime('%Y-%m-%d'), 'restored_ok': restored, 'results': results,
              'detected': sum(r['detected'] for r in results), 'total': len(results)}
    a.out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(f"detected {report['detected']}/{report['total']}; restored_ok={restored}")


if __name__ == '__main__':
    main()
