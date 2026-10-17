/**
 * Switch — binary toggle with role="switch" (design-system v2). Replaces the bespoke
 * div-and-span toggles that had no accessible state.
 * @module components/ui/Switch
 */
import { useId } from 'react';
import type { ReactNode } from 'react';
import { twMerge } from 'tailwind-merge';

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
  className?: string;
}

export function Switch({ checked, onChange, label, disabled, className }: SwitchProps) {
  const id = useId();
  return (
    <div className={twMerge('flex items-center justify-between gap-3', className)}>
      <label htmlFor={id} className="text-xs text-ink-soft">{label}</label>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={twMerge(
          'relative h-5 w-9 shrink-0 rounded-full transition-colors',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 disabled:opacity-40',
          checked ? 'bg-brand-500' : 'bg-surface-hover',
        )}
      >
        <span
          aria-hidden
          className={twMerge(
            'absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-ink-base shadow transition-transform',
            checked ? 'translate-x-4' : 'translate-x-0',
          )}
        />
      </button>
    </div>
  );
}

export default Switch;
