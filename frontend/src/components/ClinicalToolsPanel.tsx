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
import type { ClinicalToolInfo, ToolTaskResult, ToolTaskStatus } from '@/types';

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
      case 'completed': return 'text-green-400';
      case 'failed': return 'text-red-400';
      case 'processing': return 'text-yellow-400';
      default: return 'text-blue-400';
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
      <div className="py-4 text-center text-gray-400 text-xs">
        {t('clinical.loading', 'Loading tools...')}
      </div>
    );
  }

  return (
    <div className="py-2 space-y-3">
      {/* Research disclaimer */}
      <div className="bg-yellow-900/30 border border-yellow-700/50 rounded p-2">
        <p className="text-[10px] text-yellow-300/80">
          {t('clinical.researchOnly', 'Research Use Only - Not FDA Cleared')}
        </p>
      </div>

      {/* FLAMeS Card — featured single-FLAIR SOTA segmenter */}
      <div className="bg-surface-raised rounded-lg border border-brand-700/50 p-3 space-y-2 ring-1 ring-brand-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <h4 className="text-xs font-semibold text-white">FLAMeS</h4>
            <span className="text-[8px] uppercase tracking-wide px-1 py-0.5 rounded bg-brand-500/15 text-brand-400 border border-brand-500/30">
              {t('clinical.recommended', 'Recommended')}
            </span>
          </div>
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
            flamesTool?.available
              ? 'bg-green-900/50 text-green-400 border border-green-700/50'
              : 'bg-gray-700 text-gray-500 border border-gray-600'
          }`}>
            {flamesTool?.available ? t('clinical.available', 'Available') : t('clinical.unavailable', 'Unavailable')}
          </span>
        </div>
        <p className="text-[10px] text-gray-400">
          {t('clinical.flamesDesc', 'One-click MS lesion segmentation from FLAIR alone. State-of-the-art nnU-Net (Dice 0.74), outperforms LST-AI / SAMSEG.')}
        </p>
        <p className="text-[9px] text-gray-500 italic">
          {t('clinical.requires', 'Requires')}: FLAIR
        </p>

        <div className="space-y-1">
          <label className="text-[10px] text-gray-300">FLAIR:</label>
          <select
            value={flairFileId}
            onChange={(e) => setFlairFileId(e.target.value)}
            className="w-full px-2 py-1 bg-gray-700 border border-gray-600 rounded text-[10px] text-white"
          >
            <option value="">{t('clinical.selectFile', 'Select file...')}</option>
            {allFileIds.map(fid => (
              <option key={fid} value={fid}>
                {fileSeqLabel(fid)} {shortName(fid)}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleRunFLAMeS}
          disabled={!flamesTool?.available || !flairFileId || (flamesTask?.status === 'processing' || flamesTask?.status === 'storing' || flamesTask?.status === 'downloading')}
          className="w-full px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors"
        >
          {flamesTask?.status === 'processing' || flamesTask?.status === 'storing' || flamesTask?.status === 'downloading'
            ? t('clinical.running', 'Running...')
            : t('clinical.runFLAMeS', 'Auto-segment MS lesions')
          }
        </button>

        {flamesTask && (
          <TaskProgress task={flamesTask} getStatusColor={getStatusColor} getStatusLabel={getStatusLabel} />
        )}
      </div>

      {/* LST-AI Card */}
      <div className="bg-gray-800 rounded border border-gray-700 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-white">LST-AI</h4>
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
            lstaiTool?.available
              ? 'bg-green-900/50 text-green-400 border border-green-700/50'
              : 'bg-gray-700 text-gray-500 border border-gray-600'
          }`}>
            {lstaiTool?.available ? t('clinical.available', 'Available') : t('clinical.unavailable', 'Unavailable')}
          </span>
        </div>
        <p className="text-[10px] text-gray-400">
          {t('clinical.lstaiDesc', 'MS lesion segmentation + MAGNIMS zone classification')}
        </p>
        <p className="text-[9px] text-gray-500 italic">
          {t('clinical.requires', 'Requires')}: T1w + FLAIR
        </p>

        {/* File selection */}
        <div className="space-y-1">
          <label className="text-[10px] text-gray-300">T1-weighted:</label>
          <select
            value={t1FileId}
            onChange={(e) => setT1FileId(e.target.value)}
            className="w-full px-2 py-1 bg-gray-700 border border-gray-600 rounded text-[10px] text-white"
          >
            <option value="">{t('clinical.selectFile', 'Select file...')}</option>
            {allFileIds.map(fid => (
              <option key={fid} value={fid}>
                {fileSeqLabel(fid)} {shortName(fid)}
              </option>
            ))}
          </select>

          <label className="text-[10px] text-gray-300">FLAIR:</label>
          <select
            value={flairFileId}
            onChange={(e) => setFlairFileId(e.target.value)}
            className="w-full px-2 py-1 bg-gray-700 border border-gray-600 rounded text-[10px] text-white"
          >
            <option value="">{t('clinical.selectFile', 'Select file...')}</option>
            {allFileIds.map(fid => (
              <option key={fid} value={fid}>
                {fileSeqLabel(fid)} {shortName(fid)}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleRunLSTAI}
          disabled={!lstaiTool?.available || !t1FileId || !flairFileId || (lstaiTask?.status === 'processing' || lstaiTask?.status === 'downloading')}
          className="w-full px-3 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors"
        >
          {lstaiTask?.status === 'processing' || lstaiTask?.status === 'downloading'
            ? t('clinical.running', 'Running...')
            : t('clinical.runLSTAI', 'Run LST-AI Segmentation')
          }
        </button>

        {/* Progress */}
        {lstaiTask && (
          <TaskProgress task={lstaiTask} getStatusColor={getStatusColor} getStatusLabel={getStatusLabel} />
        )}
      </div>

      {/* SynthSeg Card */}
      <div className="bg-gray-800 rounded border border-gray-700 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-white">SynthSeg</h4>
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
            synthSegTool?.available
              ? 'bg-green-900/50 text-green-400 border border-green-700/50'
              : 'bg-gray-700 text-gray-500 border border-gray-600'
          }`}>
            {synthSegTool?.available ? t('clinical.available', 'Available') : t('clinical.unavailable', 'Unavailable')}
          </span>
        </div>
        <p className="text-[10px] text-gray-400">
          {t('clinical.synthsegDesc', 'Brain parcellation (30+ structures, any contrast)')}
        </p>

        <div className="space-y-1">
          <label className="text-[10px] text-gray-300">{t('clinical.inputImage', 'Input image')}:</label>
          <select
            value={synthSegFileId}
            onChange={(e) => setSynthSegFileId(e.target.value)}
            className="w-full px-2 py-1 bg-gray-700 border border-gray-600 rounded text-[10px] text-white"
          >
            <option value="">{t('clinical.selectFile', 'Select file...')}</option>
            {allFileIds.map(fid => (
              <option key={fid} value={fid}>
                {fileSeqLabel(fid)} {shortName(fid)}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleRunSynthSeg}
          disabled={!synthSegTool?.available || !synthSegFileId || (synthSegTask?.status === 'processing' || synthSegTask?.status === 'downloading')}
          className="w-full px-3 py-2 bg-teal-600 hover:bg-teal-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors"
        >
          {synthSegTask?.status === 'processing' || synthSegTask?.status === 'downloading'
            ? t('clinical.running', 'Running...')
            : t('clinical.runSynthSeg', 'Run Brain Parcellation')
          }
        </button>

        {synthSegTask && (
          <TaskProgress task={synthSegTask} getStatusColor={getStatusColor} getStatusLabel={getStatusLabel} />
        )}
      </div>

      {/* Citation footer */}
      {(flamesTool || lstaiTool) && (
        <div className="text-[8px] text-gray-600 leading-tight">
          {flamesTool && <p>FLAMeS: {flamesTool.citation}</p>}
          {lstaiTool && <p className="mt-0.5">LST-AI: {lstaiTool.citation}</p>}
          {synthSegTool && <p className="mt-0.5">SynthSeg: {synthSegTool.citation}</p>}
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
    <div className="space-y-1">
      {/* Progress bar */}
      <div className="w-full bg-gray-700 rounded-full h-1.5">
        <div
          className={`h-1.5 rounded-full transition-all duration-500 ${
            task.status === 'completed' ? 'bg-green-500'
            : task.status === 'failed' ? 'bg-red-500'
            : 'bg-blue-500'
          }`}
          style={{ width: `${Math.max(task.progress, 2)}%` }}
        />
      </div>

      {/* Status line */}
      <div className="flex items-center justify-between">
        <span className={`text-[10px] font-medium ${getStatusColor(task.status)}`}>
          {getStatusLabel(task.status)}
        </span>
        <span className="text-[10px] text-gray-500">
          {task.progress.toFixed(0)}%
        </span>
      </div>

      {/* Error message */}
      {task.status === 'failed' && task.error && (
        <p className="text-[10px] text-red-400 bg-red-900/20 rounded p-1.5 break-words">
          {task.error}
        </p>
      )}

      {/* Completed result */}
      {task.status === 'completed' && (
        <div className="bg-green-900/20 border border-green-700/30 rounded p-1.5">
          <p className="text-[10px] text-green-400">
            Segmentation ready: {task.segmentation_id?.slice(0, 8)}...
          </p>
          {task.processing_time_ms && (
            <p className="text-[9px] text-gray-500">
              {(task.processing_time_ms / 1000).toFixed(1)}s
            </p>
          )}
          <p className="text-[9px] text-gray-500 mt-0.5">
            Source: {task.validation_source}
          </p>
        </div>
      )}
    </div>
  );
};
