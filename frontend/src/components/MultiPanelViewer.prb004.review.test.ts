// @vitest-environment node
/**
 * PRB-004 — independent review of PR #71 (m7): the multi-panel grid had a mask-overlay path (no grid check,
 * arbitrary label colours) that no caller wired. REQ-SAFE-041 now states that the grid draws no segmentation;
 * the dead path is removed so that wiring a mask later cannot bring the hazard back unnoticed.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';

describe('PRB-004 review — multi-panel draws no segmentation', () => {
  it('prb004 MultiPanelViewer has no mask overlay path', () => {
    const src = readFileSync(join(__dirname, 'MultiPanelViewer.tsx'), 'utf-8');
    expect(src).not.toMatch(/segmentationMask/);
    expect(src).not.toMatch(/renderSegOverlayOnCtx/);
  });
});
