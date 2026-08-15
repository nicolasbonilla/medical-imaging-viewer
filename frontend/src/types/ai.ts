/**
 * AI: interactive/auto segmentation, brain volumetry, report generation, edge screening.
 *
 * Split out of the former single types/index.ts barrel (Fase 2.1) — re-exported
 * from ./index.ts, so `@/types` consumers are unchanged.
 */

import type { LabelInfo, Segmentation } from './segmentation';

// ============================================================================
// AI Segmentation Types
// ============================================================================

export type AIModel = 'sam_med3d' | 'nninteractive' | 'synthseg' | 'mindglide';

export type AITaskStatus = 'pending' | 'processing' | 'completed' | 'failed';

export type AIMode = 'interactive' | 'auto' | null;

export interface ClickPoint3D {
  x: number;
  y: number;
  z: number;
  label: 'positive' | 'negative';
}

export interface InteractiveSegmentRequest {
  file_id: string;
  click_points: ClickPoint3D[];
  model: AIModel;
  current_mask_id?: string;
}

export interface AutoSegmentRequest {
  file_id: string;
  model: AIModel;
}

export interface AITaskResult {
  task_id: string;
  status: AITaskStatus;
  progress: number;
  segmentation_id?: string;
  error?: string;
  processing_time_ms?: number;
}

export interface BrainAnomaly {
  type: 'ms_lesion' | 'active_lesion' | 'chronic_lesion' | 'black_hole';
  location: string;
  confidence: number;
  volume_mm3?: number;
  gadolinium_enhancement?: boolean;
  bounding_box?: {
    x_min: number; y_min: number; z_min: number;
    x_max: number; y_max: number; z_max: number;
  };
}

export interface AnomalyDetectionResult {
  anomalies: BrainAnomaly[];
  heatmap_segmentation_id?: string;
  overall_confidence: number;
  processing_time_ms?: number;
}

export interface AIModelInfo {
  id: string;
  name: string;
  type: 'interactive' | 'auto';
  description: string;
  prompt_types?: string[];
  structures_count?: number;
  configured: boolean;
}

/**
 * SynthSeg brain structure labels (FreeSurfer convention).
 * Used when loading auto-segmentation results from AI.
 */
export const BRAIN_STRUCTURE_LABELS: LabelInfo[] = [
  { id: 0,  name: 'Background', color: '#000000', opacity: 0.0, visible: false },
  { id: 2,  name: 'L Cerebral WM', color: '#F5F5DC', opacity: 0.5, visible: true, snomed_code: '61392005' },
  { id: 3,  name: 'L Cerebral Cortex', color: '#CD853F', opacity: 0.5, visible: true, snomed_code: '68594002' },
  { id: 4,  name: 'L Lateral Ventricle', color: '#4169E1', opacity: 0.6, visible: true, snomed_code: '66720007' },
  { id: 5,  name: 'L Inf Lat Ventricle', color: '#6495ED', opacity: 0.5, visible: true },
  { id: 7,  name: 'L Cerebellum WM', color: '#F0E68C', opacity: 0.5, visible: true },
  { id: 8,  name: 'L Cerebellum Cortex', color: '#BDB76B', opacity: 0.5, visible: true },
  { id: 10, name: 'L Thalamus', color: '#2E8B57', opacity: 0.6, visible: true, snomed_code: '42695009' },
  { id: 11, name: 'L Caudate', color: '#00CED1', opacity: 0.6, visible: true, snomed_code: '11000004' },
  { id: 12, name: 'L Putamen', color: '#FF69B4', opacity: 0.6, visible: true, snomed_code: '89278009' },
  { id: 13, name: 'L Pallidum', color: '#FF1493', opacity: 0.6, visible: true },
  { id: 14, name: '3rd Ventricle', color: '#1E90FF', opacity: 0.5, visible: true },
  { id: 15, name: '4th Ventricle', color: '#00BFFF', opacity: 0.5, visible: true },
  { id: 16, name: 'Brain Stem', color: '#8B4513', opacity: 0.5, visible: true, snomed_code: '15926001' },
  { id: 17, name: 'L Hippocampus', color: '#FFD700', opacity: 0.7, visible: true, snomed_code: '5366008' },
  { id: 18, name: 'L Amygdala', color: '#FF8C00', opacity: 0.7, visible: true, snomed_code: '4958002' },
  { id: 24, name: 'CSF', color: '#87CEEB', opacity: 0.4, visible: true },
  { id: 26, name: 'L Accumbens', color: '#DA70D6', opacity: 0.6, visible: true },
  { id: 28, name: 'L VentralDC', color: '#9370DB', opacity: 0.5, visible: true },
  { id: 41, name: 'R Cerebral WM', color: '#FFFACD', opacity: 0.5, visible: true },
  { id: 42, name: 'R Cerebral Cortex', color: '#DEB887', opacity: 0.5, visible: true },
  { id: 43, name: 'R Lateral Ventricle', color: '#6495ED', opacity: 0.6, visible: true },
  { id: 44, name: 'R Inf Lat Ventricle', color: '#87CEFA', opacity: 0.5, visible: true },
  { id: 46, name: 'R Cerebellum WM', color: '#EEE8AA', opacity: 0.5, visible: true },
  { id: 47, name: 'R Cerebellum Cortex', color: '#D2B48C', opacity: 0.5, visible: true },
  { id: 49, name: 'R Thalamus', color: '#3CB371', opacity: 0.6, visible: true },
  { id: 50, name: 'R Caudate', color: '#48D1CC', opacity: 0.6, visible: true },
  { id: 51, name: 'R Putamen', color: '#FF69B4', opacity: 0.6, visible: true },
  { id: 52, name: 'R Pallidum', color: '#FF1493', opacity: 0.6, visible: true },
  { id: 53, name: 'R Hippocampus', color: '#FFD700', opacity: 0.7, visible: true },
  { id: 54, name: 'R Amygdala', color: '#FF8C00', opacity: 0.7, visible: true },
  { id: 58, name: 'R Accumbens', color: '#DA70D6', opacity: 0.6, visible: true },
  { id: 60, name: 'R VentralDC', color: '#9370DB', opacity: 0.5, visible: true },
];

// ============================================================================
// Brain Volumetry Types
// ============================================================================

export interface BrainStructureVolume {
  label_id: number;
  structure_name: string;
  volume_mm3: number;
  volume_ml: number;
  normative_percentile?: number;
  is_abnormal: boolean;
  abnormality_type?: 'atrophy' | 'enlargement';
}

export interface VolumetryResult {
  segmentation_id: string;
  structures: BrainStructureVolume[];
  total_brain_volume_ml?: number;
  intracranial_volume_ml?: number;
  /** Brain Parenchymal Fraction (brain / ICV) — head-size-normalized atrophy
   *  metric standard in MS (SIENAX/icobrain/NeuroQuant). Dimensionless 0..1. */
  brain_parenchymal_fraction?: number | null;
  processing_time_ms?: number;
}

export interface VolumetryChange {
  /** null for whole-brain PBVC / BPF rows; a FreeSurfer label id for structures. */
  label_id: number | null;
  structure: string;
  /** Present on whole-brain rows: 'total_brain_volume_ml' | 'brain_parenchymal_fraction'. */
  metric?: string;
  volume_first_ml?: number;
  volume_last_ml?: number;
  value_first?: number;
  value_last?: number;
  change_percent: number;
  /** %/year, using the timepoint dates. null when dates are missing/equal. */
  annualized_change_percent?: number | null;
  /** True when annualized atrophy passes the ~-0.4%/yr MS/SIENA threshold. */
  is_pathological_atrophy?: boolean;
  trend: 'stable' | 'increasing' | 'decreasing';
}

export interface VolumetryComparisonResult {
  patient_id: string;
  /** Elapsed years between first and last timepoint; null if dates missing. */
  interval_years?: number | null;
  timepoints: Array<{ study_id: string; date: string }>;
  changes: VolumetryChange[];
}

export interface VolumetryRequest {
  segmentation_id: string;
  voxel_spacing?: [number, number, number];
  patient_age?: number;
  patient_sex?: 'M' | 'F';
}

// ============================================================================
// AI Report Types
// ============================================================================

export type ReportTemplateType = 'general' | 'ms_activity' | 'ms_comprehensive' | 'ms_lesion_burden' | 'ms_longitudinal';

export interface ReportGenerateRequest {
  template_type: ReportTemplateType;
  language: string;
  findings: Record<string, any>;
  volumetry?: Record<string, any> | null;
}

export interface ReportResponse {
  report_id: string;
  content: string;
  template_type: ReportTemplateType;
  language: string;
  processing_time_ms: number;
  model?: string;
  tokens_used?: { input: number; output: number };
}

export interface ReportTemplateInfo {
  id: ReportTemplateType;
  name: string;
  description: string;
}

// ============================================================================
// Edge AI Types (Browser-based ONNX screening)
// ============================================================================

export interface EdgeAIScreeningResult {
  normal: number;
  abnormal: number;
  inferenceTimeMs: number;
  label: 'normal' | 'abnormal';
  confidence: number;
}
