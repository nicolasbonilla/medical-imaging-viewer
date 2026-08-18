/**
 * Button — the app's primitive action control (design-system v2).
 *
 * Replaces the ~dozens of bespoke inline `<button style={{…}}>` one-offs the design
 * audit flagged: every button re-implemented hover/active/disabled/loading and most
 * had NO focus-visible ring (a WCAG 2.4.7 / keyboard-a11y gap). This bakes in one
 * radius scale, consistent states, a proper `focus-visible` ring, and a loading
 * spinner, on the v2 graphite + single-accent tokens.
 *
 * @module components/ui/Button
 */
import { forwardRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { twMerge } from 'tailwind-merge';
import { Loader2 } from 'lucide-react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle';
type Size = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  fullWidth?: boolean;
}

const BASE =
  'relative inline-flex items-center justify-center gap-2 font-medium select-none ' +
  'rounded-lg border transition-[background,border-color,color,box-shadow] duration-150 ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 focus-visible:ring-offset-2 ' +
  'focus-visible:ring-offset-surface-void disabled:opacity-50 disabled:pointer-events-none ' +
  'active:translate-y-px';

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-brand-500 hover:bg-brand-400 text-surface-void border-transparent shadow-sm ' +
    'shadow-brand-500/20',
  secondary:
    'bg-surface-raised hover:bg-surface-hover text-ink-base border-surface-border',
  subtle:
    'bg-surface-base hover:bg-surface-raised text-ink-soft border-transparent',
  ghost:
    'bg-transparent hover:bg-surface-raised text-ink-soft hover:text-ink-base border-transparent',
  danger:
    'bg-transparent hover:bg-error-500/10 text-error-400 hover:text-error-300 border-error-500/30',
};

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-2.5 text-xs',
  md: 'h-9 px-3.5 text-sm',
  lg: 'h-11 px-5 text-[15px]',
};

/**
 * The app-wide button primitive. `loading` shows a spinner and keeps width stable so
 * the layout does not shift; content is hidden (not unmounted) while loading.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading = false, leftIcon, rightIcon,
    fullWidth, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={twMerge(BASE, VARIANTS[variant], SIZES[size], fullWidth && 'w-full', className)}
      {...rest}
    >
      {loading && (
        <Loader2 className="absolute h-4 w-4 animate-spin" aria-hidden />
      )}
      <span className={twMerge('inline-flex items-center gap-2', loading && 'invisible')}>
        {leftIcon}
        {children}
        {rightIcon}
      </span>
    </button>
  );
});

export default Button;
