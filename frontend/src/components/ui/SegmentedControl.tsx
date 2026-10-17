/**
 * SegmentedControl — mutually exclusive options as one pill (radio-group semantics,
 * arrow-key navigation). Used for 2D/3D, plane, layout choices.
 * @module components/ui/SegmentedControl
 */
import { useRef } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { twMerge } from 'tailwind-merge';

export interface SegmentOption<T extends string> {
  value: T;
  label: ReactNode;
  /** Accessible name when `label` is an icon, and tooltip. */
  title?: string;
  disabled?: boolean;
}

export interface SegmentedControlProps<T extends string> {
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: 'sm' | 'md';
  className?: string;
}

export function SegmentedControl<T extends string>({
  value, options, onChange, ariaLabel, size = 'md', className,
}: SegmentedControlProps<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const enabled = options.filter((o) => !o.disabled);
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    e.stopPropagation();
    const idx = enabled.findIndex((o) => o.value === value);
    let next = idx;
    if (e.key === 'ArrowLeft') next = (idx - 1 + enabled.length) % enabled.length;
    if (e.key === 'ArrowRight') next = (idx + 1) % enabled.length;
    if (e.key === 'Home') next = 0;
    if (e.key === 'End') next = enabled.length - 1;
    const opt = enabled[next];
    if (opt) {
      onChange(opt.value);
      refs.current[options.indexOf(opt)]?.focus();
    }
  };
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={twMerge('inline-flex items-center gap-0.5 rounded-lg border border-surface-border bg-surface-base p-0.5', className)}
    >
      {options.map((o, i) => {
        const checked = o.value === value;
        return (
          <button
            key={o.value}
            ref={(el) => { refs.current[i] = el; }}
            type="button"
            role="radio"
            aria-checked={checked}
            aria-label={o.title}
            title={o.title}
            tabIndex={checked ? 0 : -1}
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            className={twMerge(
              'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 disabled:opacity-40',
              size === 'sm' ? 'h-6 px-2 text-xs' : 'h-7 px-2.5 text-xs',
              checked
                ? 'bg-surface-hover text-ink-base shadow-sm'
                : 'text-ink-muted hover:text-ink-base',
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export default SegmentedControl;
