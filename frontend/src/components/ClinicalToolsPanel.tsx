/**
 * ClinicalToolsPanel - Validated Clinical Tools Interface.
 *
 * Provides UI for invoking LST-AI (MS lesion segmentation) and
 * SynthSeg (brain parcellation) via Docker sidecar containers.
 *
 * All tool outputs include validation metadata (tool version,
 * citation, regulatory status) for clinical transparency.
 *
 * @module components/ClinicalToolsPanel
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { clinicalToolsAPI } from '@/api/clinicalTools';
import { useViewerStore } from '@/store/useViewerStore';
import { detectSequence, type SequenceType, SEQUENCE_INFO } from '@/utils/sequenceDetection';
import { Badge, Button, Skeleton } from '@/components/ui';
import type { ClinicalToolInfo, ToolTaskResult, ToolTaskStatus } from '@/types';

/** Shared styling for the compact file pickers inside the tool cards. */
const SELECT_CLASS =
  'w-full h-8 px-2 rounded-md border border-surface-border bg-surface-base text-xs text-ink-base ' +
  'transition-colors hover:border-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60';

/** Neutral tool card (FLAMeS overrides the border to mark it as recommended). */
const CARD_CLASS = 'rounded-lg border bg-surface-base/60 p-3 space-y-2';

interface ClinicalToolsPanelProps {
  fileId?: string;
}

export const ClinicalToolsPanel: React.FC<ClinicalToolsPanelProps> = ({ fileId }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const allFileIds = useViewerStore((s) => s.allFileIds);
  const currentSeries = useViewerStore((s) => s.currentSeries);

  // Tool availability
  const { data: tools, isLoading: toolsLoading } = useQuery<ClinicalToolInfo[]>({
    queryKey: ['clinical-tools'],
    queryFn: () => clinicalToolsAPI.listTools(),
    staleTime: 60_000,
  });

  // LST-AI state
  const [t1FileId, setT1FileId] = useState<string>('');
  const [flairFileId, setFlairFileId] = useState<string>('');
  const [lstaiTask, setLstaiTask] = useState<ToolTaskResult | null>(null);

  // FLAMeS state (single-FLAIR SOTA — reuses flairFileId)
  const [flamesTask, setFlamesTask] = useState<ToolTaskResult | null>(null);

  // SynthSeg state
  const [synthSegFileId, setSynthSegFileId] = useState<string>('');
  const [synthSegTask, setSynthSegTask] = useState<ToolTaskResult | null>(null);

  // Polling refs
  const lstaiPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const flamesPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const synthSegPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Auto-detect T1 and FLAIR from filenames
  useEffect(() => {
    if (allFileIds.length === 0) return;

    let foundT1 = '';
    let foundFlair = '';

    for (const fid of allFileIds) {
      const seq = detectSequence(fid);
      if (seq === 'T1w' && !foundT1) foundT1 = fid;
      if (seq === 'FLAIR' && !foundFlair) foundFlair = fid;
    }

    if (foundT1) setT1FileId(foundT1);
    if (foundFlair) setFlairFileId(foundFlair);

    // Default SynthSeg to current file
    if (fileId) setSynthSegFileId(fileId);
  }, [allFileIds, fileId]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (lstaiPollRef.current) clearInterval(lstaiPollRef.current);
      if (flamesPollRef.current) clearInterval(flamesPollRef.current);
      if (synthSegPollRef.current) clearInterval(synthSegPollRef.current);
    };
  }, []);

  const pollTask = useCallback((
    taskId: string,
    setTask: React.Dispatch<React.SetStateAction<ToolTaskResult | null>>,
    pollRef: React.MutableRefObject<ReturnType<typeof setInterval> | null>,
    onComplete?: (task: ToolTaskResult) => void,
  ) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await clinicalToolsAPI.getTaskStatus(taskId);
        setTask(status);
        if (status.status === 'completed' || status.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          if (status.status === 'completed') onComplete?.(status);
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }, 3000);
  }, []);

  // When an auto-segmentation lands, refresh the viewer's segmentation list so the
  // new mask is immediately loadable (React Query cache key is ['segmentations', fileId]).
  const refreshSegmentations = useCallback((segFileId: string) => {
    queryClient.invalidateQueries({ queryKey: ['segmentations', segFileId] });
    if (fileId && fileId !== segFileId) {
      queryClient.invalidateQueries({ queryKey: ['segmentations', fileId] });
    }
  }, [queryClient, fileId]);

  const handleRunFLAMeS = useCallback(async () => {
    if (!flairFileId) return;
    try {
      const task = await clinicalToolsAPI.runFLAMeS(flairFileId);
      setFlamesTask(task);
      if (task.status !== 'completed' && task.status !== 'failed') {
        pollTask(task.task_id, setFlamesTask, flamesPollRef,
          () => refreshSegmentations(flairFileId));
      } else if (task.status === 'completed') {
        refreshSegmentations(flairFileId);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setFlamesTask({
        task_id: '', tool: 'flames', status: 'failed',
        progress: 0, error: msg, validation_source: 'flames-v1.0',
        created_at: new Date().toISOString(),
      });
    }
  }, [flairFileId, pollTask, refreshSegmentations]);

  const handleRunLSTAI = useCallback(async () => {
    if (!t1FileId || !flairFileId) return;
    try {
      const task = await clinicalToolsAPI.runLSTAI(t1FileId, flairFileId);
      setLstaiTask(task);
      if (task.status !== 'completed' && task.status !== 'failed') {
        pollTask(task.task_id, setLstaiTask, lstaiPollRef);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setLstaiTask({
        task_id: '', tool: 'lst-ai', status: 'failed',
        progress: 0, error: msg, validation_source: 'lst-ai-v1.0.3',
        created_at: new Date().toISOString(),
      });
    }
  }, [t1FileId, flairFileId, pollTask]);

  const handleRunSynthSeg = useCallback(async () => {
    if (!synthSegFileId) return;
    try {
      const task = await clinicalToolsAPI.runSynthSeg(synthSegFileId);
      setSynthSegTask(task);
      if (task.status !== 'completed' && task.status !== 'failed') {
        pollTask(task.task_id, setSynthSegTask, synthSegPollRef);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setSynthSegTask({
        task_id: '', tool: 'synthseg', status: 'failed',
        progress: 0, error: msg, validation_source: 'synthseg-v2.0',
        created_at: new Date().toISOString(),
      });
    }
  }, [synthSegFileId, pollTask]);

  const flamesTool = tools?.find(t => t.id === 'flames');
  const lstaiTool = tools?.find(t => t.id === 'lst-ai');
  const synthSegTool = tools?.find(t => t.id === 'synthseg');

  const getStatusColor = (status: ToolTaskStatus): string => {
    switch (status) {
      case 'completed': return 'text-clinical-good';
      case 'failed': return 'text-clinical-crit';
      case 'processing': return 'text-clinical-warn';
      default: return 'text-clinical-info';
    }
  };

  const getStatusLabel = (status: ToolTaskStatus): string => {
    const labels: Record<ToolTaskStatus, string> = {
      pending: t('clinical.pending', 'Pending'),
      downloading: t('clinical.downloading', 'Downloading'),
      processing: t('clinical.processing', 'Processing'),
      storing: t('clinical.storing', 'Storing'),
      completed: t('clinical.completed', 'Completed'),
      failed: t('clinical.failed', 'Failed'),
    };
    return labels[status] || status;
  };

  // File ID → short display name
  const shortName = (fid: string): string => {
    const parts = fid.split('/');
    const fname = parts[parts.length - 1] || fid;
    return fname.length > 30 ? '...' + fname.slice(-28) : fname;
  };

  const fileSeqLabel = (fid: string): string => {
    const seq = detectSequence(fid);
    return seq !== 'unknown' ? SEQUENCE_INFO[seq].shortLabel : '';
  };

  if (toolsLoading) {
    return (
      <div className="py-2 space-y-3" role="status" aria-live="polite">
        <span className="sr-only">{t('clinical.loading', 'Loading tools...')}</span>
        <Skeleton className="h-8 w-full rounded-lg" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-lg border border-surface-border bg-surface-base/60 p-3 space-y-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-2/3" />
            <Skeleton className="h-8 w-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="py-2 space-y-3">
      {/* Research disclaimer */}
      <div className="rounded-lg border border-clinical-warn/30 bg-clinical-warn/10 px-2.5 py-2">
        <p className="text-xs font-medium text-clinical-warn">
          {t('clinical.researchOnly', 'Research Use Only - Not FDA Cleared')}
        </p>
      </div>

      {/* FLAMeS Card — featured single-FLAIR SOTA segmenter */}
      <div className={`${CARD_CLASS} border-brand-500/30`}>
        <div className="flex flex-wrap items-center justify-between gap-1.5">
          <div className="flex items-center gap-1.5">
            <h4 className="text-sm font-semibold text-ink-base">FLAMeS</h4>
            <Badge tone="brand" className="text-xs">
              {t('clinical.recommended', 'Recommended')}
            </Badge>
          </div>
          <Badge tone={flamesTool?.available ? 'good' : 'neutral'} dot className="text-xs">
            {flamesTool?.available ? t('clinical.available', 'Available') : t('clinical.unavailable', 'Unavailable')}
          </Badge>
        </div>
        <p className="text-xs leading-relaxed text-ink-muted">
          {t('clinical.flamesDesc', 'One-click MS lesion segmentation from FLAIR alone. State-of-the-art nnU-Net (Dice 0.74), outperforms LST-AI / SAMSEG.')}
        </p>
        <p className="text-xs text-ink-faint italic">
          {t('clinical.requires', 'Requires')}: FLAIR
        </p>

        <label className="block space-y-1">
          <span className="block text-xs text-ink-soft">FLAIR:</span>
          <select
            value={flairFileId}
            onChange={(e) => setFlairFileId(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">{t('clinical.selectFile', 'Select file...')}</option>
            {allFileIds.map(fid => (
              <option key={fid} value={fid}>
                {fileSeqLabel(fid)} {shortName(fid)}
              </option>
            ))}
          </select>
        </label>

        <Button
          variant="primary"
          size="sm"
          fullWidth
          onClick={handleRunFLAMeS}
          disabled={!flamesTool?.available || !flairFileId || (flamesTask?.status === 'processing' || flamesTask?.status === 'storing' || flamesTask?.status === 'downloading')}
        >
          {flamesTask?.status === 'processing' || flamesTask?.status === 'storing' || flamesTask?.status === 'downloading'
            ? t('clinical.running', 'Running...')
            : t('clinical.runFLAMeS', 'Auto-segment MS lesions')
          }
        </Button>

        {flamesTask && (
          <TaskProgress task={flamesTask} getStatusColor={getStatusColor} getStatusLabel={getStatusLabel} />
        )}
      </div>

      {/* LST-AI Card */}
      <div className={`${CARD_CLASS} border-surface-border`}>
        <div className="flex flex-wrap items-center justify-between gap-1.5">
          <h4 className="text-sm font-semibold text-ink-base">LST-AI</h4>
          <Badge tone={lstaiTool?.available ? 'good' : 'neutral'} dot className="text-xs">
            {lstaiTool?.available ? t('clinical.available', 'Available') : t('clinical.unavailable', 'Unavailable')}
          </Badge>
        </div>
        <p className="text-xs leading-relaxed text-ink-muted">
          {t('clinical.lstaiDesc', 'MS lesion segmentation + MAGNIMS zone classification')}
        </p>
        <p className="text-xs text-ink-faint italic">
          {t('clinical.requires', 'Requires')}: T1w + FLAIR
        </p>

        {/* File selection */}
        <div className="space-y-2">
          <label className="block space-y-1">
            <span className="block text-xs text-ink-soft">T1-weighted:</span>
            <select
              value={t1FileId}
              onChange={(e) => setT1FileId(e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="">{t('clinical.selectFile', 'Select file...')}</option>
              {allFileIds.map(fid => (
                <option key={fid} value={fid}>
                  {fileSeqLabel(fid)} {shortName(fid)}
                </option>
              ))}
            </select>
          </label>

          <label className="block space-y-1">
            <span className="block text-xs text-ink-soft">FLAIR:</span>
            <select
              value={flairFileId}
              onChange={(e) => setFlairFileId(e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="">{t('clinical.selectFile', 'Select file...')}</option>
              {allFileIds.map(fid => (
                <option key={fid} value={fid}>
                  {fileSeqLabel(fid)} {shortName(fid)}
                </option>
              ))}
            </select>
          </label>
        </div>

        <Button
          variant="secondary"
          size="sm"
          fullWidth
          onClick={handleRunLSTAI}
          disabled={!lstaiTool?.available || !t1FileId || !flairFileId || (lstaiTask?.status === 'processing' || lstaiTask?.status === 'downloading')}
        >
          {lstaiTask?.status === 'processing' || lstaiTask?.status === 'downloading'
            ? t('clinical.running', 'Running...')
            : t('clinical.runLSTAI', 'Run LST-AI Segmentation')
          }
        </Button>

        {/* Progress */}
        {lstaiTask && (
          <TaskProgress task={lstaiTask} getStatusColor={getStatusColor} getStatusLabel={getStatusLabel} />
        )}
      </div>

      {/* SynthSeg Card */}
      <div className={`${CARD_CLASS} border-surface-border`}>
        <div className="flex flex-wrap items-center justify-between gap-1.5">
          <h4 className="text-sm font-semibold text-ink-base">SynthSeg</h4>
          <Badge tone={synthSegTool?.available ? 'good' : 'neutral'} dot className="text-xs">
            {synthSegTool?.available ? t('clinical.available', 'Available') : t('clinical.unavailable', 'Unavailable')}
          </Badge>
        </div>
        <p className="text-xs leading-relaxed text-ink-muted">
          {t('clinical.synthsegDesc', 'Brain parcellation (30+ structures, any contrast)')}
        </p>

        <label className="block space-y-1">
          <span className="block text-xs text-ink-soft">{t('clinical.inputImage', 'Input image')}:</span>
          <select
            value={synthSegFileId}
            onChange={(e) => setSynthSegFileId(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">{t('clinical.selectFile', 'Select file...')}</option>
            {allFileIds.map(fid => (
              <option key={fid} value={fid}>
                {fileSeqLabel(fid)} {shortName(fid)}
              </option>
            ))}
          </select>
        </label>

        <Button
          variant="secondary"
          size="sm"
          fullWidth
          onClick={handleRunSynthSeg}
          disabled={!synthSegTool?.available || !synthSegFileId || (synthSegTask?.status === 'processing' || synthSegTask?.status === 'downloading')}
        >
          {synthSegTask?.status === 'processing' || synthSegTask?.status === 'downloading'
            ? t('clinical.running', 'Running...')
            : t('clinical.runSynthSeg', 'Run Brain Parcellation')
          }
        </Button>

        {synthSegTask && (
          <TaskProgress task={synthSegTask} getStatusColor={getStatusColor} getStatusLabel={getStatusLabel} />
        )}
      </div>

      {/* Citation footer */}
      {(flamesTool || lstaiTool) && (
        <div className="text-xs leading-snug text-ink-faint break-words">
          {flamesTool && <p>FLAMeS: {flamesTool.citation}</p>}
          {lstaiTool && <p className="mt-1">LST-AI: {lstaiTool.citation}</p>}
          {synthSegTool && <p className="mt-1">SynthSeg: {synthSegTool.citation}</p>}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// Task Progress Sub-component
// ============================================================================

interface TaskProgressProps {
  task: ToolTaskResult;
  getStatusColor: (status: ToolTaskStatus) => string;
  getStatusLabel: (status: ToolTaskStatus) => string;
}

const TaskProgress: React.FC<TaskProgressProps> = ({ task, getStatusColor, getStatusLabel }) => {
  return (
    <div className="space-y-1.5">
      {/* Progress bar */}
      <div className="w-full bg-surface-hover rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-1.5 rounded-full transition-all duration-500 ${
            task.status === 'completed' ? 'bg-clinical-good'
            : task.status === 'failed' ? 'bg-clinical-crit'
            : 'bg-brand-500'
          }`}
          style={{ width: `${Math.max(task.progress, 2)}%` }}
        />
      </div>

      {/* Status line */}
      <div className="flex items-center justify-between">
        <span className={`text-xs font-medium ${getStatusColor(task.status)}`}>
          {getStatusLabel(task.status)}
        </span>
        <span className="text-xs tabular-nums text-ink-faint">
          {task.progress.toFixed(0)}%
        </span>
      </div>

      {/* Error message */}
      {task.status === 'failed' && task.error && (
        <p className="text-xs text-clinical-crit bg-clinical-crit/10 border border-clinical-crit/30 rounded-md p-1.5 break-words">
          {task.error}
        </p>
      )}

      {/* Completed result */}
      {task.status === 'completed' && (
        <div className="bg-clinical-good/10 border border-clinical-good/30 rounded-md p-1.5">
          <p className="text-xs text-clinical-good">
            Segmentation ready: <span className="font-mono">{task.segmentation_id?.slice(0, 8)}</span>...
          </p>
          {task.processing_time_ms && (
            <p className="text-xs tabular-nums text-ink-faint">
              {(task.processing_time_ms / 1000).toFixed(1)}s
            </p>
          )}
          <p className="text-xs text-ink-faint mt-0.5 break-words">
            Source: {task.validation_source}
          </p>
        </div>
      )}
    </div>
  );
};
