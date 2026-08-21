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
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="seg-conflict-title"
        >
          <motion.div
            className="w-full max-w-md rounded-lg bg-slate-800 shadow-xl ring-1 ring-amber-500/40"
            initial={{ scale: 0.95, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: 8 }}
          >
            <div className="flex items-start gap-3 border-b border-slate-700 p-4">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" aria-hidden />
              <div className="flex-1">
                <h2 id="seg-conflict-title" className="text-sm font-semibold text-amber-200">
                  Segmentation changed elsewhere
                </h2>
                <p className="mt-1 text-xs leading-relaxed text-slate-300">
                  {conflict}
                </p>
              </div>
              <button
                type="button"
                onClick={handleDismiss}
                disabled={busy}
                className="rounded p-1 text-slate-400 hover:text-slate-200 disabled:opacity-50"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-2 p-4">
              <p className="text-xs text-slate-400">
                Your local edits are kept. Choose how to reconcile:
              </p>

              {!confirmingDiscard ? (
                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={handleDismiss}
                    disabled={busy}
                    className="w-full rounded-md bg-slate-700 px-3 py-2 text-sm font-medium text-slate-100 hover:bg-slate-600 disabled:opacity-50"
                  >
                    Keep editing
                  </button>
                  <button
                    type="button"
                    onClick={once(onOverwrite)}
                    disabled={busy}
                    className="w-full rounded-md bg-amber-600 px-3 py-2 text-sm font-medium text-white hover:bg-amber-500 disabled:opacity-50"
                  >
                    {busy ? 'Saving…' : 'Overwrite the newer version with my edits'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingDiscard(true)}
                    disabled={busy}
                    className="w-full rounded-md px-3 py-2 text-sm font-medium text-red-300 hover:bg-red-500/10 disabled:opacity-50"
                  >
                    Discard my edits and reload…
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-2 rounded-md bg-red-500/10 p-3 ring-1 ring-red-500/30">
                  <p className="text-xs font-medium text-red-200">
                    This permanently discards your local edits and undo history and
                    loads the other session's mask. This cannot be undone.
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setConfirmingDiscard(false)}
                      disabled={busy}
                      className="flex-1 rounded-md bg-slate-700 px-3 py-2 text-sm font-medium text-slate-100 hover:bg-slate-600 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={once(onDiscardReload)}
                      disabled={busy}
                      className="flex-1 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                    >
                      {busy ? 'Reloading…' : 'Discard & reload'}
                    </button>
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
