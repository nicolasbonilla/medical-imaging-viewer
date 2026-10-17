/**
 * Menu — a small popover menu anchored to a trigger (click-outside + Escape close,
 * focus returns to the trigger). Items can be actions or radio choices.
 *
 * The panel is rendered in a portal with fixed positioning, so it is never clipped by
 * a scrolling / overflow-hidden ancestor (e.g. the viewer toolbar strip).
 * @module components/ui/Menu
 */
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
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
  const [pos, setPos] = useState<{ top: number; left?: number; right?: number } | null>(null);
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open || !rootRef.current) return;
    const r = rootRef.current.getBoundingClientRect();
    setPos(align === 'end'
      ? { top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) }
      : { top: r.bottom + 6, left: Math.max(8, r.left) });
  }, [open, align]);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        (rootRef.current?.querySelector('[aria-haspopup="menu"]') as HTMLElement | null)?.focus();
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', close);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      {trigger({ onClick: () => setOpen((o) => !o), 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-controls': id })}
      {open && pos && createPortal(
        <div
          ref={panelRef}
          id={id}
          role="menu"
          style={{ position: 'fixed', top: pos.top, left: pos.left, right: pos.right }}
          className={twMerge(
            'z-[60] min-w-[15rem] rounded-xl border border-surface-border bg-surface-overlay p-1.5 shadow-xl shadow-black/50',
            className,
          )}
        >
          {children(() => setOpen(false))}
        </div>,
        document.body,
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
