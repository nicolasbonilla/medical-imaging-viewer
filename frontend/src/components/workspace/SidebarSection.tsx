/**
 * Collapsible sidebar section (v3 workspace): one header pattern for every group in
 * the study rail — icon, title, count, chevron — with proper button/expanded semantics.
 */
import { useId } from 'react';
import type { ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { twMerge } from 'tailwind-merge';

export function SidebarSection({
  title, icon, count, open, onToggle, actions, children, className,
}: {
  title: string;
  icon: ReactNode;
  count?: number;
  open: boolean;
  onToggle: () => void;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <section className={twMerge('border-b border-surface-border', className)}>
      <div className="flex items-center gap-1 px-3 pt-2.5">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={id}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md py-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
        >
          <span className="text-ink-muted" aria-hidden>{icon}</span>
          <span className="text-xs font-semibold uppercase tracking-wide text-ink-soft">{title}</span>
          {count !== undefined && (
            <span className="rounded-full bg-surface-raised px-1.5 text-xs tabular-nums text-ink-muted">{count}</span>
          )}
          <ChevronDown
            className={twMerge('ml-auto h-4 w-4 text-ink-faint transition-transform', !open && '-rotate-90')}
            aria-hidden
          />
        </button>
        {actions}
      </div>
      <div id={id} hidden={!open} className="px-3 pb-3 pt-2">
        {open && children}
      </div>
    </section>
  );
}

export default SidebarSection;
