/**
 * Menu — a small popover menu anchored to a trigger (click-outside + Escape close,
 * focus returns to the trigger). Items can be actions or radio choices.
 * @module components/ui/Menu
 */
import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Check } from 'lucide-react';
import { twMerge } from 'tailwind-merge';

export interface MenuProps {
  /** Renders the trigger; spread `props` onto a button. */
  trigger: (props: {
    onClick: () => void;
    'aria-haspopup': 'menu';
    'aria-expanded': boolean;
    'aria-controls': string;
  }) => ReactNode;
  children: (close: () => void) => ReactNode;
  align?: 'start' | 'end';
  className?: string;
}

export function Menu({ trigger, children, align = 'start', className }: MenuProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        (rootRef.current?.querySelector('[aria-haspopup="menu"]') as HTMLElement | null)?.focus();
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);
  return (
    <div ref={rootRef} className="relative">
      {trigger({ onClick: () => setOpen((o) => !o), 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-controls': id })}
      {open && (
        <div
          id={id}
          role="menu"
          className={twMerge(
            'absolute top-full z-50 mt-1.5 min-w-[15rem] rounded-xl border border-surface-border bg-surface-overlay p-1.5 shadow-xl shadow-black/50',
            align === 'end' ? 'right-0' : 'left-0',
            className,
          )}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return <div className="px-2.5 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-ink-faint">{children}</div>;
}

export function MenuSeparator() {
  return <div role="separator" className="my-1 h-px bg-surface-border" />;
}

export function MenuItem({
  children, description, checked, onSelect, disabled, radio = false,
}: {
  children: ReactNode;
  description?: ReactNode;
  checked?: boolean;
  onSelect: () => void;
  disabled?: boolean;
  radio?: boolean;
}) {
  return (
    <button
      type="button"
      role={radio ? 'menuitemradio' : 'menuitem'}
      aria-checked={radio ? !!checked : undefined}
      disabled={disabled}
      onClick={onSelect}
      className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-ink-soft transition-colors hover:bg-surface-hover hover:text-ink-base focus:outline-none focus-visible:bg-surface-hover disabled:opacity-40"
    >
      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
        {checked && <Check className="h-4 w-4 text-brand-400" aria-hidden />}
      </span>
      <span className="min-w-0">
        <span className="block text-ink-base">{children}</span>
        {description && <span className="mt-0.5 block text-xs text-ink-muted">{description}</span>}
      </span>
    </button>
  );
}

export default Menu;
