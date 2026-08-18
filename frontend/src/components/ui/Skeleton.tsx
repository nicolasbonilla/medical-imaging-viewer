/**
 * Skeleton — content-shaped loading placeholder (design-system v2). The audit found ZERO
 * skeletons in the app (only spinners/blank flashes), the biggest perceived-quality gap on
 * a product with slow medical loads. Uses `animate-pulse` (which respects the OS reduce-motion
 * setting via the global MotionConfig / prefers-reduced-motion). Compose these into card /
 * table / panel placeholders that match the final layout so results fade in without a jump.
 * @module components/ui/Skeleton
 */
import type { HTMLAttributes } from 'react';
import { twMerge } from 'tailwind-merge';

export function Skeleton({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={twMerge('animate-pulse rounded-md bg-surface-raised/70', className)}
      {...rest}
    />
  );
}

/** A card-shaped skeleton for grid/list loading states (e.g. the patients grid). */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={twMerge('rounded-xl border border-surface-border bg-surface-base p-4', className)}>
      <div className="flex items-center gap-3">
        <Skeleton className="h-11 w-11 rounded-lg" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-3.5 w-2/3" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      </div>
      <div className="mt-4 space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-5/6" />
      </div>
    </div>
  );
}

/** N skeleton table rows matching a dense clinical table. */
export function SkeletonRows({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-1.5" role="status" aria-live="polite" aria-label="Loading">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={twMerge('h-4', c === 0 ? 'w-1/3' : 'flex-1')} />
          ))}
        </div>
      ))}
    </div>
  );
}

export default Skeleton;
