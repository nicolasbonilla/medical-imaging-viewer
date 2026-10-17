/**
 * Intensity histogram of the displayed slice with the active window drawn as a band
 * (v3). Bins span [min, max] of the volume (client path, real units) or 0–255 (legacy
 * 8-bit path). Drawn on canvas with the v2 tokens; no decorative gradients.
 */
import { useEffect, useRef } from 'react';
import { TOKENS } from '@/styles/tokens';
import { formatIntensity } from './windowPresets';

export interface IntensityHistogramProps {
  histogram: number[];
  /** Value range the 256 bins span. */
  range: [number, number];
  /** Active window [lo, hi] in the same units (optional). */
  window?: [number, number] | null;
  /** Value under the cursor (optional). */
  cursor?: number | null;
  ariaLabel: string;
}

export function IntensityHistogram({ histogram, range, window: win, cursor, ariaLabel }: IntensityHistogramProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [lo, hi] = range;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const padB = 16;
    const plotH = h - padB - 2;
    const span = hi - lo || 1;
    const xOf = (v: number) => ((v - lo) / span) * w;

    // Background dominated bin (the biggest one) is clipped so tissue stays readable.
    const sorted = [...histogram].sort((a, b) => b - a);
    const cap = Math.max(1, sorted[1] ?? sorted[0] ?? 1) * 1.15;

    if (win) {
      const x0 = Math.max(0, xOf(win[0])), x1 = Math.min(w, xOf(win[1]));
      ctx.fillStyle = 'rgba(53, 180, 196, 0.14)';
      ctx.fillRect(x0, 0, Math.max(1, x1 - x0), plotH);
      ctx.strokeStyle = TOKENS.brand[500];
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0 + 0.5, 0); ctx.lineTo(x0 + 0.5, plotH);
      ctx.moveTo(x1 - 0.5, 0); ctx.lineTo(x1 - 0.5, plotH);
      ctx.stroke();
    }

    const bw = w / histogram.length;
    ctx.fillStyle = TOKENS.ink.muted;
    histogram.forEach((count, i) => {
      const bh = Math.min(1, count / cap) * plotH;
      if (bh < 0.5) return;
      ctx.fillRect(i * bw, plotH - bh, Math.max(1, bw - 0.25), bh);
    });

    ctx.strokeStyle = TOKENS.surface.border;
    ctx.beginPath();
    ctx.moveTo(0, plotH + 0.5); ctx.lineTo(w, plotH + 0.5);
    ctx.stroke();

    if (cursor != null && Number.isFinite(cursor)) {
      const x = xOf(cursor);
      ctx.strokeStyle = TOKENS.brand[400];
      ctx.setLineDash([3, 2]);
      ctx.beginPath();
      ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, plotH);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.font = '12px Inter, system-ui, sans-serif';
    ctx.fillStyle = TOKENS.ink.faint;
    ctx.textBaseline = 'bottom';
    ctx.textAlign = 'left';
    ctx.fillText(formatIntensity(lo), 0, h);
    ctx.textAlign = 'right';
    ctx.fillText(formatIntensity(hi), w, h);
  }, [histogram, lo, hi, win, cursor]);

  return <canvas ref={ref} role="img" aria-label={ariaLabel} className="h-24 w-full" />;
}

export default IntensityHistogram;
