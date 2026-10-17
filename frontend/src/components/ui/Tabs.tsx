/**
 * Tabs — WAI-ARIA tablist with arrow-key navigation (design-system v2).
 * @module components/ui/Tabs
 */
import { useRef } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { twMerge } from 'tailwind-merge';

export interface TabItem<T extends string> {
  value: T;
  label: ReactNode;
  icon?: ReactNode;
}

export function Tabs<T extends string>({
  value, items, onChange, ariaLabel, idPrefix, className,
}: {
  value: T;
  items: TabItem<T>[];
  onChange: (v: T) => void;
  ariaLabel: string;
  idPrefix: string;
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKeyDown = (e: KeyboardEvent) => {
    const idx = items.findIndex((i) => i.value === value);
    let next = idx;
    if (e.key === 'ArrowRight') next = (idx + 1) % items.length;
    else if (e.key === 'ArrowLeft') next = (idx - 1 + items.length) % items.length;
    else return;
    e.preventDefault();
    e.stopPropagation();
    onChange(items[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div role="tablist" aria-label={ariaLabel} onKeyDown={onKeyDown} className={twMerge('flex items-stretch gap-1', className)}>
      {items.map((it, i) => {
        const selected = it.value === value;
        return (
          <button
            key={it.value}
            ref={(el) => { refs.current[i] = el; }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${it.value}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${it.value}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(it.value)}
            className={twMerge(
              'relative inline-flex flex-1 items-center justify-center gap-1.5 px-2 py-2.5 text-xs font-medium transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500/60',
              selected ? 'text-ink-base' : 'text-ink-muted hover:text-ink-soft',
            )}
          >
            {it.icon}
            {it.label}
            <span
              aria-hidden
              className={twMerge('absolute inset-x-2 -bottom-px h-0.5 rounded-full', selected ? 'bg-brand-500' : 'bg-transparent')}
            />
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel<T extends string>({
  value, current, idPrefix, children, className,
}: { value: T; current: T; idPrefix: string; children: ReactNode; className?: string }) {
  if (value !== current) return null;
  return (
    <div role="tabpanel" id={`${idPrefix}-panel-${value}`} aria-labelledby={`${idPrefix}-tab-${value}`} className={className}>
      {children}
    </div>
  );
}

export default Tabs;
