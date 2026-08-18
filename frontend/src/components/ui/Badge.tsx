/**
 * Badge — small status/label pill (design-system v2). Semantic tones map to the clinical
 * palette so status reads at a glance; `dot` adds a leading indicator.
 * @module components/ui/Badge
 */
import type { HTMLAttributes, ReactNode } from 'react';
import { twMerge } from 'tailwind-merge';

type Tone = 'neutral' | 'brand' | 'good' | 'warn' | 'crit' | 'info';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
}

const TONES: Record<Tone, { chip: string; dot: string }> = {
  neutral: { chip: 'bg-surface-raised text-ink-soft border-surface-border', dot: 'bg-ink-muted' },
  brand: { chip: 'bg-brand-950 text-brand-400 border-brand-500/30', dot: 'bg-brand-500' },
  good: { chip: 'bg-clinical-good/10 text-clinical-good border-clinical-good/25', dot: 'bg-clinical-good' },
  warn: { chip: 'bg-clinical-warn/10 text-clinical-warn border-clinical-warn/25', dot: 'bg-clinical-warn' },
  crit: { chip: 'bg-clinical-crit/10 text-clinical-crit border-clinical-crit/25', dot: 'bg-clinical-crit' },
  info: { chip: 'bg-clinical-info/10 text-clinical-info border-clinical-info/25', dot: 'bg-clinical-info' },
};

export function Badge({ tone = 'neutral', dot = false, className, children, ...rest }: BadgeProps) {
  const t = TONES[tone];
  return (
    <span
      className={twMerge(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none',
        t.chip, className,
      )}
      {...rest}
    >
      {dot && <span className={twMerge('h-1.5 w-1.5 rounded-full', t.dot)} aria-hidden />}
      {children}
    </span>
  );
}

export default Badge;
