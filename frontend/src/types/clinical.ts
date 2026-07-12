/**
 * Clinical tool orchestration (LST-AI, SynthSeg).
 *
 * Split out of the former single types/index.ts barrel (Fase 2.1) — re-exported
 * from ./index.ts, so `@/types` consumers are unchanged.
 */

// ============================================================================
// Clinical Tools Types (LST-AI, SynthSeg)
// ============================================================================

export interface ClinicalToolInfo {
  id: string;
  name: string;
  version: string;
  available: boolean;
  healthy?: boolean;
  description: string;
  citation: string;
  license: string;
  fda_status: 'research_only' | '510k_cleared';
  required_inputs: string[];
}

export type ToolTaskStatus =
  | 'pending'
  | 'downloading'
  | 'processing'
  | 'storing'
  | 'completed'
  | 'failed';

export interface ToolTaskResult {
  task_id: string;
  tool: string;
  status: ToolTaskStatus;
  progress: number;
  segmentation_id?: string;
  error?: string;
  processing_time_ms?: number;
  validation_source: string;
  created_at: string;
}
