/**
 * Input — the app's primitive text field (design-system v2).
 * Consistent surface, focus-visible ring, optional label / left icon / error, on the
 * graphite + single-accent tokens. Replaces the divergent inline input styles the audit
 * flagged (two disjoint systems, missing focus states).
 *
 * @module components/ui/Input
 */
import { forwardRef, useId } from 'react';
import type { InputHTMLAttributes, ReactNode } from 'react';
import { twMerge } from 'tailwind-merge';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  leftIcon?: ReactNode;
  rightSlot?: ReactNode;
  containerClassName?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, leftIcon, rightSlot, className, containerClassName, id, ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className={twMerge('w-full', containerClassName)}>
      {label && (
        <label htmlFor={inputId} className="mb-1.5 block text-xs font-medium text-ink-muted">
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
            {leftIcon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          className={twMerge(
            'h-9 w-full rounded-lg border bg-surface-base text-sm text-ink-base placeholder-ink-faint',
            'transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60',
            'disabled:opacity-50',
            leftIcon ? 'pl-10' : 'pl-3',
            rightSlot ? 'pr-10' : 'pr-3',
            error ? 'border-error-500/60 focus-visible:ring-error-500/50' : 'border-surface-border hover:border-surface-hover',
            className,
          )}
          {...rest}
        />
        {rightSlot && (
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2">{rightSlot}</span>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-error-400">{error}</p>}
    </div>
  );
});

export default Input;
