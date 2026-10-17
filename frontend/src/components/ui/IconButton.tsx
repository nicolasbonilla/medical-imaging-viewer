/**
 * IconButton — icon-only control with a MANDATORY accessible name (design-system v2).
 * The audit counted 86 `title=` vs 14 `aria-label` on viewer toolbar icons (WCAG 4.1.2):
 * here `label` is required and becomes both the aria-label and the tooltip.
 * @module components/ui/IconButton
 */
import { forwardRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { twMerge } from 'tailwind-merge';

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> {
  label: string;
  icon: ReactNode;
  active?: boolean;
  tone?: 'default' | 'danger';
  size?: 'sm' | 'md';
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, active = false, tone = 'default', size = 'md', className, type = 'button', title, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={title ?? label}
      aria-pressed={active || undefined}
      className={twMerge(
        'inline-flex shrink-0 items-center justify-center rounded-md transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60',
        'disabled:pointer-events-none disabled:opacity-40',
        size === 'sm' ? 'h-7 w-7' : 'h-8 w-8',
        active
          ? 'bg-brand-950 text-brand-400 ring-1 ring-inset ring-brand-500/40'
          : tone === 'danger'
            ? 'text-ink-muted hover:bg-clinical-crit/10 hover:text-clinical-crit'
            : 'text-ink-muted hover:bg-surface-hover hover:text-ink-base',
        className,
      )}
      {...rest}
    >
      {icon}
    </button>
  );
});

export default IconButton;
