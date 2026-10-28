/**
 * Lesion Dashboard
 *
 * Displays connected-component lesion statistics, DIS criteria badge,
 * region summary bars, size distribution, total burden, CSV export,
 * and MAGNIMS auto-classification (SynthSeg + EDT / geometric).
 * Click on a lesion row to navigate to its centroid slice.
 *
 * @module components/LesionDashboard
 */

import { useState, useCallback, useEffect, useRef, useContext, lazy, Suspense } from 'react';
import { QueryClientContext } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { MIN_VISIBLE_LESION_OPACITY, undrawnMaskValues, type UndrawnReason } from '../utils/drawnLabels';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  Activity,
  Loader2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Download,
  ChevronDown,
  ChevronUp,
  MapPin,
  Zap,
  Info,
  AlertTriangle,
} from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import {
  MAGNIMS_LESION_LABELS,
  type LesionAnalysisResult,
  type DISAssessment,
  type DISExternalEvidence,
  type DISLesionPart,
  type DISRegionCorrection,
  type LesionInfo,
  type RegionClassificationResult,
  type RemovedSmallComponents,
  type ClassificationMethod,
  type LesionAnnotation,
  type CVSSummary,
  type PRLSummary,
  isDisEvaluated,
} from '@/types';
import { AutomaticMarkingNotice } from './AutomaticMarkingNotice';
import { regionEvidence, REGION_ABBREV } from '../utils/regionEvidence';
import { FEATURES } from '../config/features';
import { fetchWithSession } from '../services/session';

// CP-SLICE-THICKNESS-001 (DRAFT, RC-058): only reachable through the flag, loaded lazily so that
// nothing of it (component, logic, evidence asset) is fetched while the flag is OFF.
const SliceThicknessReliabilityCard = lazy(() => import('./SliceThicknessReliabilityCard'));


interface LesionDashboardProps {
  segmentationId: string;
  onNavigateToSlice?: (sliceIndex: number) => void;
  /** Called after auto-classify updates the mask on the server — parent should reload mask */
  onMaskUpdated?: () => void;
  /** Storage key of the image this segmentation was drawn on (slice-thickness card, RC-055). */
  sourceFileId?: string;
  /** Instances of the current study (slice-thickness card: original FLAIR of a processed image). */
  studyInstances?: ReadonlyArray<{ gcs_object_name: string; original_filename?: string }>;
}

// MAGNIMS region legend uses the Okabe-Ito colour-blind-safe categorical palette.
// The previous red(Periventricular)/green(Juxtacortical) pairing was indistinguishable
// for the ~8% of males with red-green deficiency — a clinical-safety defect, since these
// are the two most common lesion zones and sit adjacent in the legend and table.
const REGION_COLORS: Record<string, string> = {
  Periventricular: 'bg-[#E69F00]',       // orange
  Juxtacortical: 'bg-[#56B4E9]',         // sky blue
  Infratentorial: 'bg-[#009E73]',        // bluish green
  'Deep White Matter': 'bg-[#CC79A7]',   // reddish purple
};

const REGION_TEXT_COLORS: Record<string, string> = {
  Periventricular: 'text-[#F0A800]',
  Juxtacortical: 'text-[#7FC7F0]',
  Infratentorial: 'text-[#2DBF97]',
  'Deep White Matter': 'text-[#DB93BC]',
};

function sizeColor(cat: string): string {
  if (cat === 'large') return 'text-red-400';
  if (cat === 'medium') return 'text-yellow-400';
  return 'text-gray-400';
}

function regionBarWidth(vol: number, maxVol: number): string {
  if (maxVol === 0) return '0%';
  return `${Math.max(4, (vol / maxVol) * 100)}%`;
}


/** Interpolates {{name}} placeholders left by `t` (also when no i18n instance is initialised, e.g. in tests). */
function fill(text: string, values: Record<string, unknown>): string {
  return text.replace(/{{\s*(\w+)\s*}}/g, (m, k) => (k in values ? String(values[k]) : m));
}

/**
 * Release 2026-10-25 (film capture, "DWM: 1 lesions"): a lesion count in the user's language — the `…One` text for
 * exactly one (the CLDR "one" category of en, es and de), the `…Other` text for any other count.
 */
function countText(t: TFunction, key: string, n: number, one: string, other: string): string {
  const [suffix, text] = n === 1 ? ['One', one] : ['Other', other];
  return fill(t(`${key}${suffix}`, { defaultValue: text, n }), { n });
}

/** Release 2026-10-25 (review of PR #69, B1/M3): why a confirmation is refused while lesions are not drawn. */
function undrawnText(t: TFunction, problems: UndrawnReason[] | null): string[] {
  if (problems === null) {
    return [t('disReview.undrawnMaskUnreadable', 'The open mask could not be read, so it cannot be checked that every lesion is drawn.')];
  }
  return problems.map((p) => {
    switch (p.kind) {
      case 'overlay_off':
        return t('disReview.undrawnOverlayOff', 'The segmentation overlay is switched off.');
      case 'opacity_low': {
        const vals = { pct: Math.round(p.opacity * 100), min: Math.round(MIN_VISIBLE_LESION_OPACITY * 100) };
        return fill(t('disReview.undrawnOpacityLow', { defaultValue: 'The lesion opacity ({{pct}} %) is below the visible minimum ({{min}} %).', ...vals }), vals);
      }
      case 'no_label': {
        const vals = { value: p.value };
        return fill(t('disReview.undrawnNoLabel', { defaultValue: 'Mask value {{value}} has no label in the label table (drawn in cyan, not as a region): reopen the segmentation.', ...vals }), vals);
      }
      case 'hidden': {
        const vals = { name: p.name, value: p.value };
        return fill(t('disReview.undrawnHidden', { defaultValue: '"{{name}}" (value {{value}}) is hidden with its eye toggle.', ...vals }), vals);
      }
      default: {
        const vals = { name: p.name, value: p.value };
        return fill(t('disReview.undrawnFaint', { defaultValue: '"{{name}}" (value {{value}}) is too faint to see.', ...vals }), vals);
      }
    }
  });
}

export function LesionDashboard({ segmentationId, onNavigateToSlice, onMaskUpdated, sourceFileId, studyInstances }: LesionDashboardProps) {
  const { t } = useTranslation();
  const reloadMaskCallback = useSegmentationStore((s) => s.reloadMaskCallback);
  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);
  const hasUnsavedMaskChanges = useSegmentationStore((s) => s.hasUnsavedMaskChanges);
  const [analysis, setAnalysis] = useState<LesionAnalysisResult | null>(null);
  // PRB-003 (RC-070): the DIS state always comes from the gated route. `disOk` is a result the server
  // evaluated on a segmentation a radiologist confirmed; anything else is shown as "not evaluated".
  const [dis, setDis] = useState<DISAssessment | null>(null);
  // The confirmation is bound to the OPEN mask (its SHA-256 is sent): this panel may show another, expanded
  // segmentation (review of PR #68, finding 7).
  const isOpen = currentSegmentation?.segmentation_id === segmentationId;
  // The result belongs to the SAVED mask: while the open mask has unsaved changes it is not shown.
  const disHeldForUnsavedChanges = isDisEvaluated(dis) && isOpen && hasUnsavedMaskChanges;
  const disOk = isDisEvaluated(dis) && !disHeldForUnsavedChanges ? dis : null;
  const disPending = dis && !disOk ? dis : null;
  // Finding 8: every DIS request takes a ticket; only the reply of the latest request is shown.
  const disSeq = useRef(0);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  // Capture finding F10 (release 2026-10-25): from the click until the DIS state of the confirmed mask is read,
  // the card says what is happening instead of "No radiologist has confirmed this segmentation".
  const [confirmPhase, setConfirmPhase] = useState<null | 'recording' | 'refreshing'>(null);
  // Review of PR #69, B1/M3: the reasons a confirmation was refused because lesions are not drawn.
  const [confirmRefusal, setConfirmRefusal] = useState<string[] | null>(null);
  // Review of PR #69, m1: the classified mask could not be reloaded — the view may show the mask from before.
  const [maskReloadFailed, setMaskReloadFailed] = useState(false);
  // Review of PR #69, m5: the confirmation was recorded but the DIS result could not be read back yet.
  const [confirmedUnread, setConfirmedUnread] = useState(false);
  // Review of PR #69, B1 (1): the sidebar list caches are refreshed after a classification (no provider in some tests).
  const queryClient = useContext(QueryClientContext);
  // Second review of PR #68 (N1): the radiologist acknowledges the region corrections listed (exactly these).
  const [ackedCorrections, setAckedCorrections] = useState<string | null>(null);
  const pendingRegions = disPending && 'regions' in disPending ? disPending.regions ?? null : null;
  const correctionsDigest = pendingRegions?.correction_count ? pendingRegions.corrections_sha256 ?? null : null;
  // Third review of PR #68 (m-1): every list names a lesion as the lesion table does (its number and the slice its row
  // opens); a component below the lesion-size floor, which the table leaves out, is a "small component".
  const correctionText = useCallback((c: DISRegionCorrection) => {
    const v = { n: c.lesion, slice: c.slice + 1, voxels: c.voxels, from: c.classified_region_name, to: c.current_region_name };
    return c.small_component
      ? fill(t('disReview.smallComponentCorrection', { defaultValue: 'Small component ({{voxels}} voxels, slice {{slice}}): {{from}} → {{to}}', ...v }), v)
      : fill(t('disReview.correctionItem', { defaultValue: 'Lesion {{n}} (slice {{slice}}, {{voxels}} voxels): {{from}} → {{to}}', ...v }), v);
  }, [t]);
  const partText = useCallback((p: DISLesionPart) => {
    const v = { n: p.lesion, slice: p.slice + 1, voxels: p.voxels, label: p.label_name };
    return p.small_component
      ? fill(t('disReview.smallComponentPart', { defaultValue: 'Small component ({{voxels}} voxels, slice {{slice}}): {{label}}', ...v }), v)
      : fill(t('disReview.lesionPart', { defaultValue: 'Lesion {{n}} (slice {{slice}}, {{voxels}} voxels): {{label}}', ...v }), v);
  }, [t]);
  const [classification, setClassification] = useState<RegionClassificationResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isClassifying, setIsClassifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [highlightedLesion, setHighlightedLesion] = useState<number | null>(null);
  const [classifyMethod, setClassifyMethod] = useState<ClassificationMethod>('auto');
  const [lesionAnnotations, setLesionAnnotations] = useState<Record<number, Partial<LesionAnnotation>>>({});
  const [cvsSummary, setCvsSummary] = useState<CVSSummary | null>(null);
  const [prlSummary, setPrlSummary] = useState<PRLSummary | null>(null);
  const annotationDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // McDonald 2024 external evidence the brain MRI can't supply (spinal cord /
  // optic nerve) + supportive specificity markers. A checked box = present (true);
  // unchecked = not provided. Changing it re-queries the DIS endpoint.
  const [disEvidence, setDisEvidence] = useState<DISExternalEvidence>({});
  const [disEvidenceLoading, setDisEvidenceLoading] = useState(false);

  // PRB-003 (RC-070; review of PR #68, finding 8): the only way the panel reads the DIS state; a reply that
  // arrives after a newer request was made is dropped, so an old "met" can never replace a newer state.
  const fetchDis = useCallback(
    async (evidence?: DISExternalEvidence) => {
      const ticket = ++disSeq.current;
      const r = evidence
        ? await segmentationAPI.getDISAssessment(segmentationId, evidence)
        : await segmentationAPI.getDISAssessment(segmentationId);
      if (ticket === disSeq.current) setDis(r);
      return r;
    },
    [segmentationId],
  );

  const applyDisEvidence = useCallback(
    async (next: DISExternalEvidence) => {
      setDisEvidence(next);
      setDisEvidenceLoading(true);
      try {
        await fetchDis(next);
      } catch (e) {
        console.error('[LesionDashboard] DIS re-eval failed:', e);
      } finally {
        setDisEvidenceLoading(false);
      }
    },
    [segmentationId, fetchDis],
  );

  const toggleDisEvidence = useCallback(
    (key: keyof DISExternalEvidence) =>
      applyDisEvidence({ ...disEvidence, [key]: disEvidence[key] ? undefined : true }),
    [disEvidence, applyDisEvidence],
  );

  // Auto-populate from persisted analysis_data
  useEffect(() => {
    // Review of PR #69, M1: only the data of THIS dashboard's segmentation — never the open segmentation of another.
    const cached = currentSegmentation?.segmentation_id === segmentationId
      ? currentSegmentation?.metadata?.analysis_data
      : null;
    if (!cached) {
      setAnalysis(null);
      setDis(null);
      setClassification(null);
      setExpanded(false);
      return;
    }
    if (cached.lesion_analysis) {
      setAnalysis(cached.lesion_analysis);
      setExpanded(true);
    }
    // PRB-003 (RC-070): a DIS block stored in the metadata is never shown (see the effect below).
    if (cached.classification) setClassification(cached.classification);
    if (cached.lesion_annotations) {
      const map: Record<number, Partial<LesionAnnotation>> = {};
      for (const ann of cached.lesion_annotations) {
        map[ann.lesion_id] = ann;
      }
      setLesionAnnotations(map);
    }
    if (cached.cvs_summary) setCvsSummary(cached.cvs_summary);
    if (cached.prl_summary) setPrlSummary(cached.prl_summary);
  }, [segmentationId, currentSegmentation?.segmentation_id, currentSegmentation?.metadata?.analysis_data]);

  // PRB-003 (RC-070): read the DIS state from the gated route whenever a segmentation with stored analysis is
  // opened or its mask is saved again (modified_at) — never from the stored metadata.
  const refreshDis = useCallback(async () => {
    try {
      await fetchDis();
    } catch (e) {
      console.error('[LesionDashboard] DIS state could not be read:', e);
      setDis(null);
    }
  }, [fetchDis]);

  const modifiedAt = currentSegmentation?.metadata?.modified_at;
  useEffect(() => {
    disSeq.current += 1;   // a reply for the previous segmentation or mask is dropped
    setDis(null);
    const stored = useSegmentationStore.getState().currentSegmentation?.metadata?.analysis_data;
    if (stored?.lesion_analysis || stored?.classification) void refreshDis();
  }, [segmentationId, modifiedAt, refreshDis]);

  // After a save (or a discard) the DIS state is read again: saving a changed mask voids a confirmation.
  const hadUnsavedChanges = useRef(hasUnsavedMaskChanges);
  useEffect(() => {
    if (isOpen && hadUnsavedChanges.current && !hasUnsavedMaskChanges && dis) void refreshDis();
    hadUnsavedChanges.current = hasUnsavedMaskChanges;
  }, [isOpen, hasUnsavedMaskChanges, dis, refreshDis]);

  // RC-047 / RC-071: after the mask changed on the server (region classification), re-read the review
  // records so the AI draft banner and the store never show a confirmation the server has voided.
  const refreshReviewRecords = useCallback(async () => {
    try {
      const fresh = await segmentationAPI.getSegmentation(segmentationId);
      const store = useSegmentationStore.getState();
      const cur = store.currentSegmentation;
      if (cur && cur.segmentation_id === segmentationId) {
        store.setCurrentSegmentation({
          ...cur,
          metadata: {
            ...cur.metadata,
            ai_provenance: fresh.metadata?.ai_provenance ?? null,
            clinician_review: fresh.metadata?.clinician_review ?? null,
          },
        });
      }
      if (store.activeSegmentation && store.activeSegmentation.id === segmentationId) {
        store.setActiveSegmentation({ ...store.activeSegmentation, ai_provenance: fresh.metadata?.ai_provenance ?? null });
      }
    } catch (e) {
      console.error('[LesionDashboard] review records could not be re-read:', e);
    }
  }, [segmentationId]);

  // Capture finding F09 (release 2026-10-25): the region classification removes lesion components below the minimum
  // lesion size from the mask; the classification card, the DIS card and the confirm dialog say how many and why.
  // Review of PR #69, M1: the classification card shows this dashboard's own classification result; the DIS card and
  // the confirm dialog take the removal from the server's DIS state of THIS segmentation, which carries it only while
  // the classification record describes the current lesions.
  const removedValsOf = (r: RemovedSmallComponents | null | undefined) => (r && r.components > 0
    ? { components: r.components, voxels: r.voxels, volume: Number(r.volume_mm3.toFixed(1)), min: r.min_lesion_volume_mm3 }
    : null);
  const removedVals = removedValsOf(classification?.removed_small_components);
  const confirmRemovedVals = removedValsOf(pendingRegions?.removed_small_components);
  const removedText = removedVals
    ? fill(t('classify.removedComponents', { defaultValue: 'The region classification removed {{components}} lesion component(s) smaller than {{min}} mm³ from the mask ({{voxels}} voxels, {{volume}} mm³): they are below the minimum lesion size and are not classified. Check that none was a lesion before confirming.', ...removedVals }), removedVals)
    : null;
  const confirmRemovedText = confirmRemovedVals
    ? fill(t('disReview.removedComponents', { defaultValue: 'Before confirming: the region classification removed {{components}} lesion component(s) smaller than {{min}} mm³ ({{voxels}} voxels) from this mask; the confirmation applies to the mask without them.', ...confirmRemovedVals }), confirmRemovedVals)
    : null;

  // RC-071: a radiologist confirms a segmentation without AI provenance, for the exact saved mask.
  const confirmSegmentation = useCallback(async () => {
    const state = useSegmentationStore.getState();
    // Finding 7: the digest is that of the OPEN mask — never confirm another segmentation with it.
    if (state.hasUnsavedMaskChanges || state.currentSegmentation?.segmentation_id !== segmentationId) return;
    // N1: region corrections by hand are listed in the dialog and must have been acknowledged in the card.
    if (correctionsDigest && ackedCorrections !== correctionsDigest) return;
    // Release 2026-10-25 (review of PR #69, B1/M3): a radiologist never confirms a mask with lesions that are not
    // drawn — every value present in the open mask needs a label, visible, not too faint, with the overlay on and the
    // lesion opacity above the visible minimum. Otherwise the confirmation is refused before any dialog or request.
    setConfirmRefusal(null);
    const maskValues = state.maskValuesCallback?.() ?? null;
    const drawnSegmentation = state.activeSegmentation?.id === segmentationId;
    const undrawn = maskValues === null || !drawnSegmentation ? null : undrawnMaskValues({
      values: maskValues,
      labels: state.activeSegmentation?.labels ?? [],
      labelVisibility: state.labelVisibility,
      isOverlayVisible: state.isOverlayVisible,
      lesionOpacity: state.lesionOpacity,
    });
    if (maskReloadFailed || undrawn === null || undrawn.length > 0) {
      setConfirmRefusal([
        ...(maskReloadFailed ? [t('disReview.reloadFailedRefusal', 'The classified mask could not be reloaded: the view may show the mask from before the classification. Reopen the segmentation.')] : []),
        ...(undrawn === null || undrawn.length > 0 ? undrawnText(t, undrawn) : []),
      ]);
      return;
    }
    const listed = (pendingRegions?.corrections ?? []).map(correctionText);
    const question = t(
      'disReview.confirmQuestion',
      'Confirm that you have checked every lesion and its region on every slice of this saved segmentation? Your name, the time and the exact saved mask will be recorded; any later change of the mask cancels this confirmation.',
    );
    const dialogText = (
      correctionsDigest
        ? `${question}\n\n${fill(t('disReview.confirmCorrections', {
          defaultValue: 'You also confirm these {{count}} region correction(s) made by hand after the region classification:',
          count: pendingRegions?.correction_count ?? listed.length,
        }), {
          defaultValue: 'You also confirm these {{count}} region correction(s) made by hand after the region classification:',
          count: pendingRegions?.correction_count ?? listed.length,
        })}\n${listed.join('\n')}`
        : question
    );
    // F09: the components the classification removed are named in the dialog too.
    const ok = window.confirm(confirmRemovedText ? `${dialogText}\n\n${confirmRemovedText}` : dialogText);
    if (!ok) return;
    setConfirmBusy(true);
    setConfirmError(null);
    setConfirmPhase('recording');
    try {
      const digest = await useSegmentationStore.getState().maskDigestCallback?.();
      if (!digest) {
        throw new Error(t('disReview.maskUnreadable', 'The open mask could not be read; reload the segmentation and try again.'));
      }
      const review = correctionsDigest
        ? await segmentationAPI.confirmSegmentationReview(segmentationId, digest, correctionsDigest)
        : await segmentationAPI.confirmSegmentationReview(segmentationId, digest);
      const store = useSegmentationStore.getState();
      const cur = store.currentSegmentation;
      if (cur && cur.segmentation_id === segmentationId) {
        store.setCurrentSegmentation({ ...cur, metadata: { ...cur.metadata, clinician_review: review } });
      }
      // F10: recorded — the card says so until the DIS state of the confirmed mask is read (one request, awaited).
      setConfirmPhase('refreshing');
      try {
        await fetchDis();
      } catch (refreshError) {
        console.error('[LesionDashboard] DIS state could not be read after the confirmation:', refreshError);
        // Review of PR #69, m5: the card says the confirmation was recorded (never "not confirmed") and offers no
        // second confirmation until the next successful read.
        setConfirmedUnread(true);
      }
    } catch (e: any) {
      // The server's reason (409: classification missing, lesions without one region, corrections not acknowledged).
      setConfirmError(e?.response?.data?.error?.message || e?.response?.data?.detail || e?.message || String(e));
    } finally {
      setConfirmBusy(false);
      setConfirmPhase(null);
    }
  }, [segmentationId, fetchDis, t, correctionsDigest, ackedCorrections, pendingRegions, correctionText, confirmRemovedText,
      maskReloadFailed]);

  // m5: a new DIS state ends the "recorded, not read" state; m1: another opened segmentation ends the reload failure.
  useEffect(() => { setConfirmedUnread(false); }, [dis]);
  useEffect(() => { setMaskReloadFailed(false); }, [currentSegmentation?.segmentation_id]);

  // Stale check: mask was edited after analysis was computed
  const isAnalysisStale = !!(
    analysis &&
    currentSegmentation?.metadata?.modified_at &&
    currentSegmentation?.metadata?.analysis_data?.analysis_mask_modified_at &&
    currentSegmentation.metadata.modified_at !== currentSegmentation.metadata.analysis_data.analysis_mask_modified_at
  );

  // Helper: patch Zustand currentSegmentation with updated analysis_data
  const patchAnalysisData = useCallback((patch: Record<string, unknown>) => {
    const store = useSegmentationStore.getState();
    const cur = store.currentSegmentation;
    // Review of PR #69, M1: never write this dashboard's results into another (open) segmentation.
    if (!cur || cur.segmentation_id !== segmentationId) return;
    store.setCurrentSegmentation({
      ...cur,
      metadata: {
        ...cur.metadata,
        analysis_data: {
          ...(cur.metadata?.analysis_data || {}),
          ...patch,
          analysis_mask_modified_at: cur.metadata.modified_at,
        },
      },
    });
  }, []);

  const handleAnalyze = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [analysisResult] = await Promise.all([
        segmentationAPI.analyzeLesions(segmentationId),
        fetchDis(),
      ]);
      setAnalysis(analysisResult);
      setExpanded(true);
      patchAnalysisData({ lesion_analysis: analysisResult });
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setIsLoading(false);
    }
  }, [segmentationId, patchAnalysisData, fetchDis]);

  const handleClassifyRegions = useCallback(async () => {
    // Review of PR #69, m2: only the open segmentation without unsaved changes (it reloads the open mask).
    const st = useSegmentationStore.getState();
    if (st.currentSegmentation?.segmentation_id !== segmentationId || st.hasUnsavedMaskChanges) return;
    setIsClassifying(true);
    setError(null);
    try {
      const result = await segmentationAPI.classifyRegions(segmentationId, {
        method: classifyMethod,
      });
      setClassification(result);
      // Review of PR #69, B1 (1): the sidebar list (and the per-file lists) were fetched before the classification;
      // they are refreshed so that no later open uses the labels from before it.
      void queryClient?.invalidateQueries({ queryKey: ['segmentations'] });

      // Capture finding F08 (release 2026-10-25): the 2D canvas draws from activeSegmentation.labels. The labels the
      // server stored with the classified mask reach it (and currentSegmentation), every region visible, BEFORE the
      // mask is reloaded. Before, only currentSegmentation was updated, after the reload: lesions labelled 2-4 were not
      // drawn until the study was reopened. (NiiVue's opt-in 2D view and the 3D view do not use the label table: they
      // load the overlay once per segmentation with a fixed colormap and are not reloaded after a classification —
      // review of PR #69, m3; left to PR #71, which rewrites them.)
      if (result.labels_updated) {
        useSegmentationStore.getState().applyServerLabels(segmentationId, result.labels ?? MAGNIMS_LESION_LABELS);
      }

      if (result.mask_updated) {
        // Review of PR #69, m1: a failed reload is shown and blocks the confirmation until the segmentation is reopened.
        const reloaded = await reloadMaskCallback?.();
        if (reloaded === false) {
          setMaskReloadFailed(true);
          setError(t('classify.reloadFailed', 'The classified mask could not be reloaded: the view may show the mask from before the classification. Reopen the segmentation before checking or confirming it.'));
        } else {
          setMaskReloadFailed(false);
        }
        onMaskUpdated?.();
        // The region labels changed the mask: any confirmation of the previous mask was voided (RC-047/RC-071).
        await refreshReviewRecords();
      }

      const [analysisResult] = await Promise.all([
        segmentationAPI.analyzeLesions(segmentationId),
        fetchDis(),
      ]);
      setAnalysis(analysisResult);
      setExpanded(true);

      patchAnalysisData({
        classification: result,
        lesion_analysis: analysisResult,
      });
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setIsClassifying(false);
    }
  }, [segmentationId, classifyMethod, onMaskUpdated, reloadMaskCallback, patchAnalysisData, refreshReviewRecords, fetchDis,
      queryClient, t]);

  const handleLesionClick = useCallback((lesion: LesionInfo) => {
    const current = useSegmentationStore.getState().selectedLesion;
    if (current && current.id === lesion.id) {
      setHighlightedLesion(null);
      useSegmentationStore.getState().setSelectedLesion(null);
      return;
    }
    setHighlightedLesion(lesion.id);
    onNavigateToSlice?.(Math.round(lesion.centroid.z));
    useSegmentationStore.getState().setSelectedLesion(lesion);
  }, [onNavigateToSlice]);

  const handleExportCSV = useCallback(() => {
    if (!analysis) return;
    const headers = ['#', 'Region', 'Volume (mm\u00b3)', 'Volume (mL)', 'Size', 'Centroid Z', 'Centroid Y', 'Centroid X'];
    const quote = (v: string | number) => typeof v === 'string' && v.includes(',') ? `"${v}"` : String(v);
    const rows = analysis.lesions.map((l) => [
      l.id, l.region, l.volume_mm3, l.volume_ml, l.size_category,
      l.centroid.z, l.centroid.y, l.centroid.x,
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.map(quote).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `lesion_analysis_${segmentationId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [analysis, segmentationId]);

  /** Save CVS/PRL annotation change (debounced 1s) */
  const handleAnnotationChange = useCallback((
    lesionId: number,
    field: 'cvs_status' | 'prl_status',
    value: string | null,
  ) => {
    setLesionAnnotations((prev) => ({
      ...prev,
      [lesionId]: {
        ...prev[lesionId],
        lesion_id: lesionId,
        [field]: value,
        annotated_by: 'manual',
      },
    }));
    if (annotationDebounceRef.current) clearTimeout(annotationDebounceRef.current);
    annotationDebounceRef.current = setTimeout(async () => {
      try {
        const allAnnotations = Object.values({
          ...lesionAnnotations,
          [lesionId]: {
            ...lesionAnnotations[lesionId],
            lesion_id: lesionId,
            [field]: value,
            annotated_by: 'manual',
          },
        });
        const result = await segmentationAPI.annotateLesions(segmentationId, allAnnotations);
        setCvsSummary(result.cvs_summary);
        setPrlSummary(result.prl_summary);
        patchAnalysisData({
          lesion_annotations: allAnnotations,
          cvs_summary: result.cvs_summary,
          prl_summary: result.prl_summary,
        });
      } catch (err: any) {
        console.error('[LesionDashboard] Failed to save annotations:', err?.message || err);
      }
    }, 1000);
  }, [segmentationId, lesionAnnotations, patchAnalysisData]);

  const maxRegionVol = analysis
    ? Math.max(...Object.values(analysis.regions).map((r) => r.total_volume_mm3), 1)
    : 1;

  return (
    <div style={{ background: '#161922', borderRadius: 8, padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-amber-400" />
          <span className="text-sm font-semibold text-white">
            {t('lesions.title', 'Lesion Analysis')}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {isAnalysisStale && (
            <span className="flex items-center gap-0.5 text-[9px] text-amber-400" title="Mask was edited since last analysis">
              <AlertCircle className="w-3 h-3" /> Outdated
            </span>
          )}
          <button
            onClick={handleAnalyze}
            disabled={isLoading}
            className="px-2 py-1 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs text-white transition-colors"
          >
            {isLoading ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              t('lesions.analyze', 'Analyze')
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-1 text-red-400 text-xs">
          <AlertCircle className="w-3 h-3" />
          <span>{error}</span>
        </div>
      )}

      {/* Reliability by slice thickness (CP-SLICE-THICKNESS-001, DRAFT, flag OFF) — placed
          before the lesion table so it is read with the list, not after it. */}
      {FEATURES.SLICE_THICKNESS_RELIABILITY && (
        <Suspense fallback={null}>
          <SliceThicknessReliabilityCard sourceFileId={sourceFileId} studyInstances={studyInstances} />
        </Suspense>
      )}

      {/* ================================================================ */}
      {/* LESION TABLE — Primary view, always visible when analysis exists */}
      {/* ================================================================ */}
      {analysis && analysis.lesions.length > 0 && !disOk && (
        <div
          className="flex items-start gap-1 text-[9px] text-amber-300 bg-amber-900/20 border border-amber-700/40 rounded px-1.5 py-1"
          role="note"
          data-testid="regions-not-confirmed"
        >
          <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-px" aria-hidden="true" />
          <span>{t('disReview.regionsNotConfirmed', 'Regions not confirmed by a radiologist; not a DIS assessment.')}</span>
        </div>
      )}
      {analysis && analysis.lesions.length > 0 && (
        <div className="bg-gray-900/60 rounded-lg p-2.5 border border-gray-700/50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold text-white">
              {t('lesions.lesionTable', 'Lesion Table')}
            </span>
            <span className="text-[10px] text-gray-400 font-mono">
              {countText(t, 'lesions.count', analysis.total_count, '{{n}} lesion', '{{n}} lesions')} &middot; {analysis.total_burden_ml.toFixed(2)} mL
            </span>
          </div>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-[10px]">
              <thead className="sticky top-0 bg-gray-900/95 z-10">
                <tr className="text-gray-400 border-b border-gray-600">
                  <th className="text-left py-1 px-1.5">#</th>
                  <th className="text-left py-1 px-1.5">{t('lesions.region', 'Region')}</th>
                  <th className="text-right py-1 px-1.5">mm&sup3;</th>
                  <th className="text-right py-1 px-1.5">mL</th>
                  <th className="text-center py-1 px-1.5">{t('lesions.size', 'Size')}</th>
                </tr>
              </thead>
              <tbody>
                {analysis.lesions.map((lesion) => (
                  <tr
                    key={lesion.id}
                    onClick={() => handleLesionClick(lesion)}
                    className={`cursor-pointer border-b border-gray-800 transition-colors ${
                      highlightedLesion === lesion.id
                        ? 'bg-amber-900/40'
                        : 'hover:bg-gray-700/50'
                    }`}
                  >
                    <td className="py-1 px-1.5 text-gray-400">{lesion.id}</td>
                    <td className="py-1 px-1.5">
                      <span className="flex items-center gap-1">
                        <span className={`w-2 h-2 rounded-full ${REGION_COLORS[lesion.region] ?? 'bg-gray-500'}`} />
                        <span className="text-gray-200">{lesion.region}</span>
                      </span>
                    </td>
                    <td className="py-1 px-1.5 text-right font-mono text-gray-300">
                      {lesion.volume_mm3.toLocaleString()}
                    </td>
                    <td className="py-1 px-1.5 text-right font-mono text-white font-medium">
                      {lesion.volume_ml.toFixed(3)}
                    </td>
                    <td className={`py-1 px-1.5 text-center font-medium ${sizeColor(lesion.size_category)}`}>
                      {lesion.size_category === 'small' ? 'S' : lesion.size_category === 'medium' ? 'M' : 'L'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ================================================================ */}
      {/* Auto-Classify Regions (MAGNIMS) */}
      {/* ================================================================ */}
      <div className="bg-gray-900/60 rounded-lg p-2 space-y-2 border border-gray-700/50">
        <div className="flex items-center gap-1.5">
          <MapPin className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-white">
            {t('classify.title', 'MAGNIMS Region Classification')}
          </span>
        </div>
        <p className="text-[9px] text-gray-400 leading-relaxed">
          {t('classify.description',
            'Classify lesions into Periventricular, Juxtacortical, Infratentorial and Deep WM regions (MAGNIMS contact rule). The method used is shown with the result; verify every region before using it for DIS.'
          )}
        </p>

        {/* Method selector */}
        <div className="flex gap-1">
          {(['auto', 'msmask', 'geometric'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setClassifyMethod(m)}
              className={`flex-1 px-1.5 py-1 rounded text-[10px] transition-colors ${
                classifyMethod === m
                  ? 'bg-cyan-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
            >
              {m === 'auto'
                ? t('classify.methodAuto', 'Auto')
                : m === 'msmask'
                ? t('classify.methodMSMask', 'MSMask')
                : t('classify.methodGeometric', 'Geometric')}
            </button>
          ))}
        </div>

        {!(isOpen && !hasUnsavedMaskChanges) && (
          <p className="text-[9px] text-amber-300" data-testid="classify-needs-open-saved">
            {t('classify.needsOpenSaved', 'Open this segmentation and save your changes to classify it: the classification works on the saved mask and reloads the open one.')}
          </p>
        )}
        <button
          onClick={handleClassifyRegions}
          disabled={isClassifying || !(isOpen && !hasUnsavedMaskChanges)}
          className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs text-white font-medium transition-colors"
        >
          {isClassifying ? (
            <>
              <Loader2 className="w-3 h-3 animate-spin" />
              {t('classify.classifying', 'Classifying...')}
            </>
          ) : (
            <>
              <Zap className="w-3 h-3" />
              {t('classify.classify', 'Auto-Classify Regions')}
            </>
          )}
        </button>

        {classification && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[9px]">
              <span className="text-gray-400">
                {t('classify.method', 'Method')}: <span className="text-cyan-300 font-medium">{classification.method}</span>
              </span>
              <span className="text-gray-400">
                {classification.processing_time_ms}ms
              </span>
            </div>
            {classification.atlas_unavailable_reason && (
              <div
                className="flex items-start gap-1 text-[9px] text-amber-300 bg-amber-900/20 border border-amber-700/40 rounded px-1.5 py-1"
                role="alert"
                data-testid="atlas-unavailable"
              >
                <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-px" aria-hidden="true" />
                <span>
                  {t('classify.atlasUnavailable', 'Atlas regions not used: this image is not in MNI space, so the geometric fallback (coordinate rules, not anatomical landmarks) was applied. Verify every region before using it for DIS.')}
                </span>
              </div>
            )}
            {classification.atlas_error && (
              <div
                className="flex items-start gap-1 text-[9px] text-amber-300 bg-amber-900/20 border border-amber-700/40 rounded px-1.5 py-1"
                role="alert"
                data-testid="atlas-error"
              >
                <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-px" aria-hidden="true" />
                <span>
                  {t('classify.atlasError', 'Atlas regions could not be computed (internal error), so the geometric fallback was applied. Verify every region before using it for DIS.')}
                </span>
              </div>
            )}
            {classification.method === 'geometric' && !classification.atlas_unavailable_reason && !classification.atlas_error && (
              <div
                className="flex items-start gap-1 text-[9px] text-amber-300 bg-amber-900/20 border border-amber-700/40 rounded px-1.5 py-1"
                role="alert"
                data-testid="geometric-warning"
              >
                <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-px" aria-hidden="true" />
                <span>
                  {t('classify.geometricWarning', 'Geometric heuristics: coordinate rules, not anatomical landmarks; their accuracy has not been measured. Verify every region before using it for DIS.')}
                </span>
              </div>
            )}
            {removedText && (
              <div
                className="flex items-start gap-1 text-[9px] text-amber-300 bg-amber-900/20 border border-amber-700/40 rounded px-1.5 py-1"
                role="alert"
                data-testid="classification-removed-components"
              >
                <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-px" aria-hidden="true" />
                <span>{removedText}</span>
              </div>
            )}
            <div className="flex flex-wrap gap-x-2 gap-y-1">
              {Object.entries(classification.classification_summary).map(([region, count]) => (
                <span key={region} className="flex items-center gap-1 text-[9px]">
                  <span className={`w-2 h-2 rounded-full ${REGION_COLORS[region] ?? 'bg-gray-500'}`} />
                  <span className={REGION_TEXT_COLORS[region] ?? 'text-gray-300'}>
                    {region}: {count}
                  </span>
                </span>
              ))}
            </div>
            {classification.lesions.length > 0 && (
              <div className="text-[9px] text-gray-500" data-testid="classify-no-confidence">
                {t('classify.noConfidence', 'Regions follow a deterministic MAGNIMS rule; no per-lesion confidence is reported.')}
              </div>
            )}
          </div>
        )}
      </div>

      {/* DIS — McDonald 2024. PRB-003 (RC-070): "not evaluated" unless a radiologist confirmed this segmentation
          for its current mask; never met / not met, region presence or a topography count otherwise. */}
      {disPending ? (
        <div
          className="p-2 rounded-lg bg-amber-950/30 border border-amber-700/50 flex flex-col gap-1"
          role="status"
          data-testid="dis-not-evaluated"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" aria-hidden="true" />
            <span className="text-xs font-bold text-amber-200">
              {t('disReview.title', 'DIS (brain MRI): not evaluated')}
            </span>
          </div>
          <p className="text-[10px] text-amber-100 leading-snug">
            {t(
              'disReview.body',
              'Dissemination in space requires clinician review of the segmentation: it is evaluated only on a segmentation a radiologist has confirmed, lesion by lesion and region by region, for this exact saved mask.',
            )}
          </p>
          {(() => {
            const reason = 'not_evaluated_reason' in disPending ? disPending.not_evaluated_reason : undefined;
            const source = 'segmentation_review' in disPending ? disPending.segmentation_review?.source : undefined;
            const lesionTool = 'information_for_safety' in disPending && !!disPending.information_for_safety;
            // Blocker 1: the confirmation is offered only once the regions are classified (and, for an AI draft,
            // after its own review); finding 7: only on the open segmentation.
            const confirmable = !disHeldForUnsavedChanges
              && (reason === 'segmentation_not_confirmed' || reason === 'confirmation_outdated');
            if (confirmedUnread) {
              return (
                <p className="text-[10px] text-amber-100" role="status" data-testid="dis-confirmed-unread">
                  {t('disReview.refreshFailed', 'Your confirmation was recorded, but the DIS result could not be read; press Analyze to read it again.')}
                </p>
              );
            }
            if (confirmPhase) {
              return (
                <p className="flex items-center gap-1 text-[10px] text-amber-100" role="status" aria-live="polite"
                   data-testid="dis-confirm-pending">
                  <Loader2 className="w-3 h-3 animate-spin shrink-0" aria-hidden="true" />
                  {confirmPhase === 'recording'
                    ? t('disReview.confirmRecording', 'Recording your confirmation…')
                    : t('disReview.confirmRefreshing', 'Confirmation recorded — reading the DIS result for the confirmed mask…')}
                </p>
              );
            }
            return (
              <>
                {disHeldForUnsavedChanges ? (
                  <p className="text-[10px] text-amber-100/80" data-testid="dis-unsaved-changes">
                    {t('disReview.reasonUnsaved', 'The mask on screen has unsaved changes: the confirmation and the result apply to the saved mask only. Saving a changed mask cancels the confirmation.')}
                  </p>
                ) : reason === 'regions_not_classified' ? (
                  <p className="text-[10px] text-amber-100/80" data-testid="dis-regions-not-classified">
                    {t('disReview.reasonRegionsNotClassified', 'The lesions have no MAGNIMS regions from the region classification (or lesions changed since). Run the MAGNIMS region classification, check every region, then confirm.')}
                  </p>
                ) : reason === 'lesion_labels_invalid' ? (
                  <div className="text-[10px] text-amber-100/80" data-testid="dis-lesion-labels-invalid">
                    <p>{t('disReview.reasonLesionLabelsInvalid', 'Every connected lesion must carry exactly one region (periventricular, juxtacortical, infratentorial or deep white matter); Active (Gd+) and Black Hole (T1) are not regions. Correct these lesions, or run the region classification again:')}</p>
                    <ul className="list-disc pl-4">
                      {(pendingRegions?.invalid_lesions ?? []).map((les) => (
                        <li key={les.first_voxel.join('-')} data-testid="dis-invalid-lesion">
                          {les.parts?.length ? (
                            les.parts.map((p, i) => (
                              <div key={i} data-testid="dis-invalid-lesion-part">{partText(p)}</div>
                            ))
                          ) : fill(t('disReview.invalidLesionItem', {
                            defaultValue: 'Lesion {{n}} (slice {{slice}}, {{voxels}} voxels): {{labels}}',
                            n: les.lesion, slice: les.slice + 1, voxels: les.voxels, labels: les.label_names.join(' + '),
                          }), { n: les.lesion, slice: les.slice + 1, voxels: les.voxels, labels: les.label_names.join(' + ') })}
                        </li>
                      ))}
                    </ul>
                    {(pendingRegions?.invalid_lesion_count ?? 0) > (pendingRegions?.invalid_lesions?.length ?? 0) && (
                      <p>{fill(t('disReview.moreLesions', { defaultValue: '… and {{count}} more', count: (pendingRegions?.invalid_lesion_count ?? 0) - (pendingRegions?.invalid_lesions?.length ?? 0) }), { defaultValue: '… and {{count}} more', count: (pendingRegions?.invalid_lesion_count ?? 0) - (pendingRegions?.invalid_lesions?.length ?? 0) })}</p>
                    )}
                  </div>
                ) : reason === 'ai_review_missing' ? (
                  <p className="text-[10px] text-amber-100/80">
                    {t('disReview.reasonAiReviewMissing', 'This AI draft must first confirm its own review (AI draft banner in the segmentation panel) for the current mask.')}
                  </p>
                ) : reason === 'confirmation_outdated' ? (
                  <p className="text-[10px] text-amber-100/80">
                    {t('disReview.reasonOutdated', 'The segmentation changed after it was confirmed; the confirmation no longer applies.')}
                  </p>
                ) : (
                  <p className="text-[10px] text-amber-100/80">
                    {t('disReview.reasonNotConfirmed', 'No radiologist has confirmed this segmentation.')}
                  </p>
                )}
                <p className="text-[10px] text-amber-100/80">
                  {source === 'ai_draft'
                    ? t('disReview.sourceAiDraft', 'AI draft: check every lesion and region, then confirm the review in the AI draft banner of the segmentation panel.')
                    : source === 'automatic_tool'
                    ? t('disReview.sourceAutomatic', 'Automatic segmentation from a clinical tool: its origin is recorded, its lesions and regions are not checked.')
                    : t('disReview.sourceUnrecorded', 'The origin of this segmentation is not recorded (drawn here or uploaded from another program).')}
                </p>
                {lesionTool && <AutomaticMarkingNotice />}
                {confirmRemovedText && (
                  <p className="text-[10px] text-amber-100" data-testid="dis-removed-components">{confirmRemovedText}</p>
                )}
                {pendingRegions?.edited_after_classification && (
                  <p className="text-[10px] text-amber-100/80" data-testid="dis-edited-after-classification">
                    {t('disReview.editedAfterClassification', 'Region labels were changed by hand after the region classification.')}
                  </p>
                )}
                {!!pendingRegions?.correction_count && (
                  <div className="text-[10px] text-amber-100" data-testid="dis-region-corrections">
                    <p className="font-semibold">
                      {fill(t('disReview.correctionsTitle', {
                        defaultValue: '{{count}} lesion region(s) differ from the region classification (corrected by hand):',
                        count: pendingRegions.correction_count,
                      }), {
                        defaultValue: '{{count}} lesion region(s) differ from the region classification (corrected by hand):',
                        count: pendingRegions.correction_count,
                      })}
                    </p>
                    <ul className="list-disc pl-4">
                      {(pendingRegions.corrections ?? []).map((c) => (
                        <li key={c.first_voxel.join('-')} data-testid="dis-region-correction">
                          {correctionText(c)}
                        </li>
                      ))}
                    </ul>
                    {pendingRegions.correction_count > (pendingRegions.corrections?.length ?? 0) && (
                      <p>{fill(t('disReview.moreLesions', { defaultValue: '… and {{count}} more', count: pendingRegions.correction_count - (pendingRegions.corrections?.length ?? 0) }), { defaultValue: '… and {{count}} more', count: pendingRegions.correction_count - (pendingRegions.corrections?.length ?? 0) })}</p>
                    )}
                  </div>
                )}
                {confirmable && (
                  !isOpen ? (
                    <p className="text-[10px] text-amber-300" data-testid="dis-open-to-confirm">
                      {t('disReview.openToConfirm', 'Open this segmentation to confirm it: the confirmation is bound to the mask on screen.')}
                    </p>
                  ) : hasUnsavedMaskChanges ? (
                    <p className="text-[10px] text-amber-300" data-testid="dis-save-first">
                      {t('disReview.saveFirst', 'Unsaved changes: save them first. Only the saved mask can be confirmed.')}
                    </p>
                  ) : (
                    <>
                      {correctionsDigest && (
                        <label className="flex items-start gap-1 text-[10px] text-amber-100">
                          <input
                            type="checkbox"
                            data-testid="dis-ack-corrections"
                            checked={ackedCorrections === correctionsDigest}
                            onChange={(e) => setAckedCorrections(e.target.checked ? correctionsDigest : null)}
                          />
                          <span>{t('disReview.acknowledgeCorrections', 'I have checked these region corrections and confirm them as mine.')}</span>
                        </label>
                      )}
                      <button
                        onClick={confirmSegmentation}
                        disabled={confirmBusy || (!!correctionsDigest && ackedCorrections !== correctionsDigest)}
                        className="self-start mt-0.5 px-2 py-0.5 rounded bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-[10px] text-white"
                      >
                        {t('disReview.confirm', 'I have checked every lesion and region — confirm this segmentation')}
                      </button>
                    </>
                  )
                )}
              </>
            );
          })()}
          {confirmRefusal && (
            <div className="text-[10px] text-red-300 border border-red-700/50 rounded px-1.5 py-1" role="alert"
                 data-testid="dis-confirm-refused">
              <p className="font-semibold">
                {t('disReview.notAllDrawn', 'Not confirmed: every lesion must be drawn on screen before you confirm.')}
              </p>
              <ul className="list-disc pl-4">
                {confirmRefusal.map((line) => <li key={line}>{line}</li>)}
              </ul>
            </div>
          )}
          {confirmError && <p className="text-[10px] text-red-300">{confirmError}</p>}
        </div>
      ) : disOk ? (
        <div className={`flex items-center gap-2 p-2 rounded-lg ${
          (disOk.dis_met_brain ?? disOk.dis_met) ? 'bg-green-900/30 border border-green-700/50' : 'bg-red-900/30 border border-red-700/50'
        }`}>
          {(disOk.dis_met_brain ?? disOk.dis_met) ? (
            <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 text-red-400 shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <div className={`text-xs font-bold ${(disOk.dis_met_brain ?? disOk.dis_met) ? 'text-green-300' : 'text-red-300'}`}>
              DIS (Brain MRI): {disOk.brain_regions_with_lesions ?? disOk.regions_with_lesions}/{disOk.brain_regions_evaluated ?? 3} {t('lesions.regions', 'regions')}
              {(disOk.dis_met_brain ?? disOk.dis_met) ? ` \u2014 ${t('lesions.criterionMet', 'Criterion Met')}` : ` \u2014 ${t('lesions.criterionNotMet', 'Not Met')}`}
            </div>
            <div className="flex flex-wrap gap-x-2 gap-y-0.5 mt-1">
              {Object.entries(disOk.region_details ?? {}).map(([name, detail]) => (
                <span key={name} className="flex items-center gap-0.5 text-[9px]">
                  {detail.present ? (
                    <CheckCircle2 className="w-2.5 h-2.5 text-green-400" />
                  ) : (
                    <XCircle className="w-2.5 h-2.5 text-gray-600" />
                  )}
                  <span className={detail.present ? 'text-green-300' : 'text-gray-500'}>{name}</span>
                  {typeof detail.qualifying_lesion_count === 'number' && (
                    <span
                      className={detail.present ? 'text-green-400/80' : 'text-gray-600'}
                      title={t(
                        'lesions.qualifyingLesionsTooltip',
                        'Lesions in this region meeting the MAGNIMS size/location criteria; a region counts toward DIS when this is ≥ 1',
                      )}
                    >
                      ({detail.qualifying_lesion_count})
                    </span>
                  )}
                </span>
              ))}
            </div>
            {disOk.note && (
              <div className="text-[8px] text-gray-500 mt-1 italic">{disOk.note}</div>
            )}
            {disOk.segmentation_review && (
              <div className="text-[8px] text-green-200/80 mt-0.5" data-testid="dis-confirmed-by">
                {disOk.segmentation_review.reviewed_by
                  ? `${t('disReview.confirmedBy', 'Segmentation confirmed by')} ${disOk.segmentation_review.reviewed_by}`
                  : t('disReview.confirmedByRadiologist', 'Segmentation confirmed by a radiologist')}
              </div>
            )}
            {!!disOk.regions?.correction_count && (
              <div className="text-[8px] text-green-200/80" data-testid="dis-confirmed-corrections">
                {fill(t('disReview.confirmedCorrections', {
                  defaultValue: 'Including {{count}} region correction(s) made by hand and acknowledged in the confirmation.',
                  count: disOk.regions.correction_count,
                }), {
                  defaultValue: 'Including {{count}} region correction(s) made by hand and acknowledged in the confirmation.',
                  count: disOk.regions.correction_count,
                })}
              </div>
            )}
            {disOk.dis_criteria_version && (
              <div className="text-[7px] text-gray-600 mt-0.5">{disOk.dis_criteria_version}</div>
            )}
          </div>
        </div>
      ) : !classification && analysis && (
        <div className="flex items-center gap-2 p-2 rounded-lg bg-gray-800/50 border border-gray-700/50">
          <Info className="w-4 h-4 text-gray-500 shrink-0" />
          <span className="text-[10px] text-gray-400">
            {t('lesions.classifyFirst', 'Classify regions first to evaluate DIS criteria')}
          </span>
        </div>
      )}

      {/* McDonald 2024: five-topography integration + external evidence.
          Decision support only — never a diagnosis (CMSC guidance). */}
      {disOk && (
        <div className="p-2 rounded-lg bg-indigo-950/30 border border-indigo-800/40 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold text-indigo-200">
              {t('lesions.mcdonald2024', 'McDonald 2024 · 5 topographies')}
            </span>
            <span className="text-[10px] text-indigo-100 font-bold">
              {disOk.total_topographies_involved}/5
              {disEvidenceLoading && <span className="ml-1 text-indigo-400 animate-pulse">…</span>}
            </span>
          </div>

          {disOk.dit_waiver_supported && (
            <div className="text-[9px] text-emerald-300 bg-emerald-900/20 border border-emerald-800/40 rounded px-1.5 py-1">
              {t(
                'lesions.ditWaiver',
                '≥4 of 5 topographies — dissemination in time may be waived (2024). Clinical correlation required.',
              )}
            </div>
          )}

          {/* External evidence the brain MRI can't supply */}
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {([
              ['optic_nerve_involved', t('lesions.opticNerve', 'Optic nerve')],
              ['spinal_cord_involved', t('lesions.spinalCord', 'Spinal cord')],
              ['cvs_positive', t('lesions.cvs', 'Central vein sign')],
              ['prl_present', t('lesions.prl', 'Paramagnetic rim')],
              ['csf_specific', t('lesions.csf', 'CSF-specific (OCB/kFLC)')],
            ] as [keyof DISExternalEvidence, string][]).map(([key, label]) => (
              <label key={key} className="flex items-center gap-1 text-[9px] text-gray-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="w-3 h-3 accent-indigo-500"
                  checked={!!disEvidence[key]}
                  disabled={disEvidenceLoading}
                  onChange={() => toggleDisEvidence(key)}
                />
                {label}
              </label>
            ))}
          </div>

          {disOk.specificity_marker_present && (
            <div className="text-[9px] text-indigo-300">
              {t('lesions.specificityPresent', 'Supportive specificity marker present (adds diagnostic specificity).')}
            </div>
          )}

          <div className="text-[8px] text-gray-500 italic">
            {t(
              'lesions.decisionSupport',
              'Radiological decision support only — not a diagnosis. Requires clinical correlation by a neurologist.',
            )}
          </div>
        </div>
      )}

      {/* Additional badges (DWM, active, black holes) */}
      {disOk && (disOk.dwm_lesion_count > 0 || disOk.has_active_lesions || disOk.has_black_holes) && (
        <div className="flex flex-wrap gap-2">
          {disOk.dwm_lesion_count > 0 && (
            <span className="px-1.5 py-0.5 bg-yellow-900/40 border border-yellow-700/50 rounded text-[9px] text-yellow-300">
              {countText(t, 'lesions.dwmCount', disOk.dwm_lesion_count,
                'DWM: {{n}} lesion (not a DIS region)', 'DWM: {{n}} lesions (not a DIS region)')}
            </span>
          )}
          {disOk.has_active_lesions && (
            <span className="px-1.5 py-0.5 bg-fuchsia-900/40 border border-fuchsia-700/50 rounded text-[9px] text-fuchsia-300">
              Gd+ {t('lesions.active', 'Active')}
            </span>
          )}
          {disOk.has_black_holes && (
            <span className="px-1.5 py-0.5 bg-purple-900/40 border border-purple-700/50 rounded text-[9px] text-purple-300">
              T1 {t('lesions.blackHoles', 'Black Holes')}
            </span>
          )}
        </div>
      )}

      {/* Clinician CVS/PRL readings — McDonald 2024 supportive markers (CAPA-008: counts only) */}
      {(cvsSummary || prlSummary) && (
        <div className="bg-gray-900/60 rounded-lg p-2 space-y-1.5 border border-indigo-700/40" data-testid="cvs-prl-readings">
          <div className="flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-xs font-semibold text-white">
              {t('lesions.markerReadingsTitle', 'CVS / PRL readings (clinician)')}
            </span>
          </div>
          <div className="text-[8px] text-gray-400">
            {t('lesions.markerReadingsNote', 'Read on susceptibility-sensitive MRI. McDonald 2024 uses them as supportive evidence only in specific situations; these are counts, not a criterion.')}
          </div>

          {cvsSummary && (
            <div className="space-y-1">
              <span className="text-[9px] text-gray-400 font-medium">
                CVS (Central Vein Sign)
              </span>
              <div className="flex flex-wrap gap-1.5">
                <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${
                  cvsSummary.meets_select6
                    ? 'bg-green-900/40 text-green-300 border-green-700/50'
                    : 'bg-gray-800 text-gray-400 border-gray-700/50'
                }`}>
                  {cvsSummary.meets_select6 ? <CheckCircle2 className="w-2.5 h-2.5 inline mr-0.5" /> : <XCircle className="w-2.5 h-2.5 inline mr-0.5" />}
                  Select 6: {cvsSummary.cvs_positive}/{cvsSummary.total_evaluated} CVS+
                </span>
                <span className="px-1.5 py-0.5 rounded border text-[9px] font-medium bg-gray-800 text-gray-300 border-gray-700/50">
                  {t('lesions.cvsPosNeg', 'CVS+ {{pos}} · CVS− {{neg}}', { pos: cvsSummary.cvs_positive, neg: cvsSummary.cvs_negative })}
                </span>
              </div>
            </div>
          )}

          {prlSummary && (
            <div className="space-y-1">
              <span className="text-[9px] text-gray-400 font-medium">
                PRL (Paramagnetic Rim Lesions)
              </span>
              <div>
                {/* CAPA-008: neutral count — ">=1 PRL" is not, by itself, a criterion met. */}
                <span className="px-1.5 py-0.5 rounded border text-[9px] font-medium bg-gray-800 text-gray-300 border-gray-700/50">
                  PRL: {prlSummary.prl_positive}/{prlSummary.total_evaluated} positive
                </span>
              </div>
            </div>
          )}

          <div className="text-[7px] text-gray-600">
            Montalban et al., Lancet Neurology 2025; 24(10): 850-865
          </div>
        </div>
      )}

      {analysis && (
        <>
          {/* Total Burden + Size Distribution */}
          <div className="bg-gray-900/50 rounded-lg p-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-400">
                {t('lesions.totalBurden', 'T2 Lesion Load')}
              </span>
              <span className="text-sm font-mono font-bold text-white">
                {analysis.total_burden_ml.toFixed(2)} mL
              </span>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-[10px] text-gray-400">
                {t('lesions.totalCount', 'Total Lesions')}
              </span>
              <span className="text-xs font-mono text-white">
                {analysis.total_count}
              </span>
            </div>
            <div className="flex gap-2 text-[10px] mt-1.5 pt-1.5 border-t border-gray-700/50">
              <span className="text-gray-400">
                {t('lesions.small', 'Small')}: <span className="text-gray-300">{analysis.size_distribution.small}</span>
              </span>
              <span className="text-yellow-400">
                {t('lesions.medium', 'Medium')}: <span className="text-yellow-300">{analysis.size_distribution.medium}</span>
              </span>
              <span className="text-red-400">
                {t('lesions.large', 'Large')}: <span className="text-red-300">{analysis.size_distribution.large}</span>
              </span>
            </div>
          </div>

          {/* Region Summary Bars */}
          <div className="space-y-1">
            <label className="text-[10px] text-gray-400 block">
              {t('lesions.byRegion', 'By Region')}
            </label>
            {!disOk && (
              <p className="text-[9px] text-amber-300" data-testid="regions-not-confirmed-bars">
                {t('disReview.regionsNotConfirmed', 'Regions not confirmed by a radiologist; not a DIS assessment.')}
              </p>
            )}
            {Object.entries(analysis.regions).map(([name, region]) => (
              <div key={name} className="space-y-0.5">
                <div className="flex items-center justify-between text-[9px]">
                  <span className="flex items-center gap-1">
                    <span className={`w-1.5 h-1.5 rounded-full ${REGION_COLORS[name] ?? 'bg-gray-500'}`} />
                    <span className="text-gray-300">{name}</span>
                  </span>
                  <span className="text-gray-400">
                    {region.lesion_count} {'\u2014'} {region.total_volume_ml.toFixed(2)} mL
                  </span>
                </div>
                <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-amber-500 rounded-full transition-all"
                    style={{ width: regionBarWidth(region.total_volume_mm3, maxRegionVol) }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Classification details (expandable) */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-200 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {t('classify.distanceDetails', 'Classification Distances')} ({analysis.total_count})
          </button>

          {classification && classification.lesions.length > 0 && expanded && (
            <div className="mt-2">
              <label className="text-[10px] text-gray-400 block mb-1">
                {t('classify.distanceDetails', 'Classification Distances (mm)')}
              </label>
              <div className="max-h-36 overflow-y-auto">
                <table className="w-full text-[9px]">
                  <thead>
                    <tr className="text-gray-500 border-b border-gray-700">
                      <th className="text-left py-0.5 px-1">#</th>
                      <th className="text-left py-0.5 px-1">{t('classify.region', 'Region')}</th>
                      <th className="text-right py-0.5 px-1">PV</th>
                      <th className="text-right py-0.5 px-1">JC</th>
                      <th className="text-right py-0.5 px-1">IT</th>
                      <th
                        className="text-center py-0.5 px-1"
                        title={t('classify.inZoneTooltip', 'Fraction of the lesion inside the assigned MAGNIMS zone (MSMask). Descriptive, not a probability.')}
                      >
                        {t('classify.inZone', 'Lesion % in zone')}
                      </th>
                      <th className="text-center py-0.5 px-1">CVS</th>
                      <th className="text-center py-0.5 px-1">PRL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classification.lesions.map((cl) => (
                      <tr key={cl.lesion_id} className="border-b border-gray-800">
                        <td className="py-0.5 px-1 text-gray-400">{cl.lesion_id}</td>
                        <td className="py-0.5 px-1">
                          <span className="flex items-center gap-1">
                            <span className={`w-1.5 h-1.5 rounded-full ${REGION_COLORS[cl.region] ?? 'bg-gray-500'}`} />
                            <span className={REGION_TEXT_COLORS[cl.region] ?? 'text-gray-300'}>
                              {cl.region}
                            </span>
                          </span>
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-400">
                          {cl.distances_mm?.to_ventricle?.toFixed(1) ?? '-'}
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-400">
                          {cl.distances_mm?.to_cortex?.toFixed(1) ?? '-'}
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-400">
                          {cl.distances_mm?.to_infratentorial?.toFixed(1) ?? '-'}
                        </td>
                        <td className="py-0.5 px-1 text-center">
                          {(() => {
                            // RC-010 (amended): evidence, never a confidence (HAZ-005).
                            const ev = regionEvidence(cl);
                            if (ev.kind === 'outsideZones') {
                              return (
                                <span
                                  className="inline-flex items-center gap-0.5 text-[8px] text-amber-300"
                                  title={t('classify.outsideZonesTooltip', 'No voxel of this lesion lies in any MSMask white-matter zone (it may be cortical, intraventricular, or the atlas may be misaligned). Deep White Matter was assigned by default, not by the MAGNIMS rule. Verify the location before using it for DIS.')}
                                  data-testid="region-evidence"
                                >
                                  <AlertTriangle className="w-2.5 h-2.5" aria-hidden="true" />
                                  {t('classify.outsideZones', 'No WM zone — DWM by default')}
                                </span>
                              );
                            }
                            if (ev.kind === 'overlap') {
                              return (
                                <span
                                  className="text-[8px] font-mono text-gray-400"
                                  title={t('classify.inZoneTooltip', 'Fraction of the lesion inside the assigned MAGNIMS zone (MSMask). Descriptive, not a probability.')}
                                  data-testid="region-evidence"
                                >
                                  {t('classify.inZoneValue', '{{pct}}% in {{zone}}', {
                                    pct: Math.round(ev.value * 100),
                                    zone: REGION_ABBREV[cl.region] ?? cl.region,
                                  })}
                                </span>
                              );
                            }
                            return <span className="text-[8px] text-gray-600" data-testid="region-evidence">{'\u2014'}</span>;
                          })()}
                        </td>
                        <td className="py-0.5 px-1 text-center">
                          <select
                            value={lesionAnnotations[cl.lesion_id]?.cvs_status ?? ''}
                            onChange={(e) => handleAnnotationChange(cl.lesion_id, 'cvs_status', e.target.value || null)}
                            className="bg-gray-800 text-[8px] text-gray-300 border border-gray-700 rounded px-0.5 py-0 w-10"
                          >
                            <option value="">{'\u2014'}</option>
                            <option value="positive">+</option>
                            <option value="negative">{'\u2212'}</option>
                            <option value="indeterminate">?</option>
                          </select>
                        </td>
                        <td className="py-0.5 px-1 text-center">
                          <select
                            value={lesionAnnotations[cl.lesion_id]?.prl_status ?? ''}
                            onChange={(e) => handleAnnotationChange(cl.lesion_id, 'prl_status', e.target.value || null)}
                            className="bg-gray-800 text-[8px] text-gray-300 border border-gray-700 rounded px-0.5 py-0 w-10"
                          >
                            <option value="">{'\u2014'}</option>
                            <option value="positive">+</option>
                            <option value="negative">{'\u2212'}</option>
                            <option value="indeterminate">?</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Export CSV */}
          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300 transition-colors"
          >
            <Download className="w-3 h-3" />
            {t('lesions.exportCSV', 'Export CSV')}
          </button>

          {/* Export DICOM-SEG */}
          <button
            onClick={() => {
              const url = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/v1/segmentation/${segmentationId}/export/dicom-seg`;
              const toastId = toast.loading(t('lesions.exportingSeg', 'Exporting DICOM-SEG…'));
              fetchWithSession(url)   // CAPA-015 RC-069: silent refresh / re-login on 401
                .then(res => {
                  if (!res.ok) throw new Error(`Export failed (${res.status})`);
                  return res.blob();
                })
                .then(blob => {
                  const a = document.createElement('a');
                  a.href = URL.createObjectURL(blob);
                  a.download = `${segmentationId}_seg.dcm`;
                  a.click();
                  URL.revokeObjectURL(a.href);
                  toast.success(t('lesions.exportSegOk', 'DICOM-SEG exported'), { id: toastId });
                })
                // A clinical data export must NEVER fail silently (Class C): surface it.
                .catch((e) => toast.error(
                  t('lesions.exportSegFail', 'DICOM-SEG export failed') +
                  (e?.message ? `: ${e.message}` : ''), { id: toastId }));
            }}
            className="flex items-center gap-1 px-2 py-1 bg-blue-700/50 hover:bg-blue-600/50 rounded text-[10px] text-blue-300 transition-colors"
          >
            <Download className="w-3 h-3" />
            DICOM-SEG
          </button>
        </>
      )}
    </div>
  );
}
