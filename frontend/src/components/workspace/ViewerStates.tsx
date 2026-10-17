/** Full-screen states of the viewer route (no study / loading / error), v2 tokens. */
import { useTranslation } from 'react-i18next';
import { AlertCircle, ArrowLeft } from 'lucide-react';
import { Button, Skeleton } from '../ui';

export function ViewerMessage({
  tone, title, body, actionLabel, onAction,
}: { tone: 'warn' | 'crit'; title: string; body: string; actionLabel: string; onAction: () => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-surface-void px-6 text-center">
      <AlertCircle className={`mb-4 h-12 w-12 ${tone === 'warn' ? 'text-clinical-warn' : 'text-clinical-crit'}`} aria-hidden />
      <h2 className="mb-2 font-display text-xl font-semibold text-ink-base">{title}</h2>
      <p className="mb-6 max-w-md text-sm text-ink-muted">{body}</p>
      <Button variant="primary" onClick={onAction} leftIcon={<ArrowLeft className="h-4 w-4" aria-hidden />}>
        {actionLabel}
      </Button>
    </div>
  );
}

/** Workspace-shaped skeleton while the study loads (no layout jump when it arrives). */
export function ViewerLoading() {
  const { t } = useTranslation();
  return (
    <div className="flex h-screen flex-col bg-surface-void" role="status" aria-live="polite">
      <span className="sr-only">{t('viewer.loadingStudy', 'Loading study...')}</span>
      <div className="h-[92px] shrink-0 border-b border-surface-border bg-surface-base" />
      <div className="flex min-h-0 flex-1">
        <div className="w-[316px] shrink-0 space-y-3 border-r border-surface-border bg-surface-base p-3">
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-3 w-28" />
          <Skeleton className="h-9 w-full" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="h-12 shrink-0 border-b border-surface-border bg-surface-base" />
          <div className="grid flex-1 place-items-center bg-black">
            <Skeleton className="aspect-square w-[min(48vh,520px)] rounded-3xl" />
          </div>
          <div className="h-8 shrink-0 border-t border-surface-border bg-surface-base" />
        </div>
        <div className="w-[300px] shrink-0 space-y-3 border-l border-surface-border bg-surface-base p-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-40 w-full rounded-lg" />
          <Skeleton className="h-28 w-full rounded-lg" />
        </div>
      </div>
    </div>
  );
}
