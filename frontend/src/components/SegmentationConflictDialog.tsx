/**
 * SegmentationConflictDialog — A-2 optimistic-concurrency reconciliation.
 *
 * Shown when the server refuses a save (409) because another session persisted a
 * newer mask since this one loaded. The clinician's local edits are ALWAYS kept
 * (never silently discarded); this dialog is the ONLY place the two safe
 * resolutions are offered:
 *
 *   1. Keep editing        — dismiss, retry later or export first (default/safe).
 *   2. Overwrite           — deliberately persist the local edits over the newer
 *                            server version (X-Overwrite).
 *   3. Discard & reload     — DESTRUCTIVE: drop local edits + undo history and load
 *                            the server's newer mask. Gated behind an explicit
 *                            second confirmation because it destroys annotator work
 *                            (Class C: no silent data loss).
 *
 * @module components/SegmentationConflictDialog
 */

import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, X } from 'lucide-react';
import { Button } from '@/components/ui';

interface SegmentationConflictDialogProps {
  /** The conflict message from the server, or null when there is no conflict. */
  conflict: string | null;
  /** True while a save/overwrite/reload request is in flight (disables actions). */
  busy?: boolean;
  /** Deliberately overwrite the newer server version with the local edits. */
  onOverwrite: () => void;
  /** Discard local edits + undo history and reload the server's newer mask. */
  onDiscardReload: () => void;
  /** Dismiss and keep editing locally (no save). */
  onDismiss: () => void;
}

export function SegmentationConflictDialog({
  conflict,
  busy = false,
  onOverwrite,
  onDiscardReload,
  onDismiss,
}: SegmentationConflictDialogProps) {
  // Two-step guard so the destructive Reload cannot be a single mis-click.
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  // Synchronous in-flight latch: `busy` (from React state) only flips after a
  // re-render, so a fast double-click could dispatch two requests before it does.
  const inFlightRef = useRef(false);

  const open = conflict !== null;

  // Release the latch once the in-flight request settles (busy → false) or the
  // dialog closes, so a FAILED overwrite (which reopens the conflict) can be
  // retried. `busy` only changes after a re-render, so this never fires in the
  // same tick as the click that set the latch.
  useEffect(() => {
    if (!busy || !open) inFlightRef.current = false;
  }, [busy, open]);

  const once = (fn: () => void) => () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    fn();
  };

  const handleDismiss = () => {
    setConfirmingDiscard(false);
    onDismiss();
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-surface-void/70 p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="seg-conflict-title"
        >
          <motion.div
            className="w-full max-w-md rounded-xl border border-surface-border bg-surface-overlay shadow-2xl shadow-black/40"
            initial={{ scale: 0.95, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: 8 }}
          >
            <div className="flex items-start gap-3 border-b border-surface-border p-4">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-clinical-warn/30 bg-clinical-warn/10">
                <AlertTriangle className="h-4 w-4 text-clinical-warn" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <h2 id="seg-conflict-title" className="text-sm font-semibold text-ink-base">
                  Segmentation changed elsewhere
                </h2>
                <p className="mt-1 text-xs leading-relaxed text-ink-soft">
                  {conflict}
                </p>
              </div>
              <button
                type="button"
                onClick={handleDismiss}
                disabled={busy}
                className="rounded-md p-1 text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 disabled:opacity-50"
                aria-label="Close"
                title="Close"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>

            <div className="space-y-3 p-4">
              <p className="text-xs text-ink-muted">
                Your local edits are kept. Choose how to reconcile:
              </p>

              {!confirmingDiscard ? (
                <div className="flex flex-col gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    fullWidth
                    onClick={handleDismiss}
                    disabled={busy}
                  >
                    Keep editing
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    fullWidth
                    onClick={once(onOverwrite)}
                    disabled={busy}
                    className="border-clinical-warn/40 bg-clinical-warn/10 text-clinical-warn hover:bg-clinical-warn/20"
                  >
                    {busy ? 'Saving…' : 'Overwrite the newer version with my edits'}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    fullWidth
                    onClick={() => setConfirmingDiscard(true)}
                    disabled={busy}
                    className="text-clinical-crit hover:bg-clinical-crit/10 hover:text-clinical-crit"
                  >
                    Discard my edits and reload…
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col gap-3 rounded-lg border border-clinical-crit/30 bg-clinical-crit/10 p-3">
                  <p className="text-xs font-medium leading-relaxed text-clinical-crit">
                    This permanently discards your local edits and undo history and
                    loads the other session's mask. This cannot be undone.
                  </p>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setConfirmingDiscard(false)}
                      disabled={busy}
                      className="flex-1"
                    >
                      Cancel
                    </Button>
                    <Button
                      type="button"
                      variant="primary"
                      onClick={once(onDiscardReload)}
                      disabled={busy}
                      className="flex-1 bg-clinical-crit text-surface-void shadow-clinical-crit/20 hover:bg-clinical-crit/90"
                    >
                      {busy ? 'Reloading…' : 'Discard & reload'}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default SegmentationConflictDialog;
