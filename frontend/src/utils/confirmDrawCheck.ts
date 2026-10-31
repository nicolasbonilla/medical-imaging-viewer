/**
 * The ONE check of the view on screen made before a radiologist confirms in the viewer — shared by both confirmations:
 * the DIS confirmation (LesionDashboard, RC-071) and, since PRB-029 (RC-091), the AI-draft review (AiDraftBanner,
 * RC-047), which had none.
 *
 * Read from the segmentation store at the moment Confirm is pressed:
 *  - release 2026-10-25 (review of PR #69, B1/M3; final check, R1/R2): the standard 2D view (one panel, segmentation
 *    mode on) draws this segmentation; every value of the open mask has a label there, visible and not too faint,
 *    drawn with the label the server stored for it (same name and colour); the overlay is on and the lesion opacity
 *    is at least the visible minimum (utils/drawnLabels.ts);
 *  - PRB-030 (RC-092, L1): the image that view draws under the mask has the mask's grid;
 *  - PRB-031 (RC-093, L2): no layer drawn under the lesions above MAX_UNDERLAY_OPACITY.
 * The request then carries the drawn label table and the image under the mask; the server checks both (the label
 * table against the stored one, the image header against the mask's grid). A direct API call or another client skips
 * the browser part (RMF-001, residual risk of RC-071).
 */
import type { TFunction } from 'i18next';
import type { LabelInfo } from '@/types';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import {
  CONFORMAL_TIER_OPACITY, LONGITUDINAL_OVERLAY_OPACITY, MAX_UNDERLAY_OPACITY, MIN_VISIBLE_LESION_OPACITY,
  SUBTRACTION_MAX_OPACITY, undrawnMaskValues, type UndrawnReason, type UnderlayLayer,
} from './drawnLabels';

type StoreState = ReturnType<typeof useSegmentationStore.getState>;
type StoredLabels = ReadonlyArray<Pick<LabelInfo, 'id' | 'name' | 'color'>>;

export interface ConfirmDrawCheck {
  /** every reason why the confirmation is refused; empty: accepted; null: the open mask could not be read */
  problems: UndrawnReason[] | null;
  /** the label table the mask is drawn with (its digest is sent with the confirmation) */
  drawnLabels: LabelInfo[];
  /** the image the standard 2D view draws under the mask (sent with the confirmation; the server reads its header) */
  displayedImageFileId: string | null;
}

/** PRB-031: the layers drawn under the lesions now, each with the opacity it is drawn at. */
export function underlaysOnScreen(state: StoreState): Array<{ layer: UnderlayLayer; opacity: number }> {
  const out: Array<{ layer: UnderlayLayer; opacity: number }> = [];
  if (state.zoneMapVisible && state.zoneMapMask && state.zoneMapDims) out.push({ layer: 'zone_map', opacity: state.zoneMapOpacity });
  if (state.longitudinalVisible && state.longitudinalTp1Mask && state.longitudinalTp2Mask) {
    out.push({ layer: 'longitudinal', opacity: LONGITUDINAL_OVERLAY_OPACITY });
  }
  if (state.longitudinalSubtractionVisible && state.longitudinalSubtractionVolume && state.longitudinalSubtractionDims) {
    out.push({ layer: 'subtraction', opacity: SUBTRACTION_MAX_OPACITY });
  }
  if (state.conformalVisible && state.conformalStatusMask && state.conformalDims) out.push({ layer: 'conformal', opacity: CONFORMAL_TIER_OPACITY });
  return out;
}

/**
 * The check for segmentation `segmentationId`. `storedLabels`: the label table the server stored for it, as the viewer
 * draws it (null: it could not be read — refused; undefined: not compared).
 */
export function confirmDrawCheck(segmentationId: string, storedLabels: StoredLabels | null | undefined): ConfirmDrawCheck {
  const state = useSegmentationStore.getState();
  const maskValues = state.maskValuesCallback?.() ?? null;
  const drawnSegmentation = state.activeSegmentation?.id === segmentationId;
  const image = state.overlayImageOnScreen;
  const imageHere = image && image.segmentationId === segmentationId && image.imageFileId ? image : null;
  const problems = maskValues === null || !drawnSegmentation ? null : undrawnMaskValues({
    values: maskValues,
    labels: state.activeSegmentation?.labels ?? [],
    labelVisibility: state.labelVisibility,
    isOverlayVisible: state.isOverlayVisible,
    lesionOpacity: state.lesionOpacity,
    onScreen: state.overlayOnScreen === segmentationId,
    storedLabels,
    grid: imageHere ? { image: imageHere.image, mask: imageHere.mask } : null,
    underlays: underlaysOnScreen(state),
  });
  return {
    problems,
    drawnLabels: state.activeSegmentation?.labels ?? [],
    displayedImageFileId: imageHere?.imageFileId ?? null,
  };
}

/** Interpolates {{name}} placeholders left by `t` (also when no i18n instance is initialised, e.g. in tests). */
function fill(text: string, values: Record<string, unknown>): string {
  return text.replace(/{{\s*(\w+)\s*}}/g, (m, k) => (k in values ? String(values[k]) : m));
}

const gridText = (g: { width: number; height: number; depth: number }) => `${g.width} × ${g.height} × ${g.depth}`;

const UNDERLAY_NAMES: Record<UnderlayLayer, [key: string, text: string]> = {
  zone_map: ['disReview.underlayZoneMap', 'The zone map'],
  longitudinal: ['disReview.underlayLongitudinal', 'The longitudinal overlay'],
  subtraction: ['disReview.underlaySubtraction', 'The FLAIR subtraction heat map'],
  conformal: ['disReview.underlayConformal', 'The conformal tier overlay'],
};

/**
 * Why a confirmation was refused, one line per reason, in the user's language. `storedLabelsUnknown` replaces the
 * text for labels that could not be read (it names the action of the panel that read them).
 */
export function undrawnText(t: TFunction, problems: UndrawnReason[] | null, storedLabelsUnknown?: string): string[] {
  if (problems === null) {
    return [t('disReview.undrawnMaskUnreadable', 'The open mask could not be read, so it cannot be checked that every lesion is drawn.')];
  }
  return problems.map((p) => {
    switch (p.kind) {
      case 'not_on_screen':
        return t('disReview.undrawnNotOnScreen', 'The view on screen does not draw this segmentation with its region labels. Switch to the Standard view (2D, one panel) with Segmentation mode on to confirm.');
      case 'stored_labels_unknown':
        return storedLabelsUnknown ?? t('disReview.undrawnStoredLabelsUnknown', 'The region labels stored for this segmentation could not be read, so it cannot be checked that the lesions are drawn with them: press Analyze.');
      case 'not_stored_label': {
        const vals = { value: p.value, drawn: p.drawn, drawnColor: p.drawnColor, stored: p.stored, storedColor: p.storedColor };
        return fill(t('disReview.undrawnNotStoredLabel', { defaultValue: 'Mask value {{value}} is drawn as "{{drawn}}" ({{drawnColor}}), not with the label stored for this segmentation, "{{stored}}" ({{storedColor}}): select the MAGNIMS Regional labels or reopen the segmentation.', ...vals }), vals);
      }
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
      case 'grid_unknown':
        return t('disReview.undrawnGridUnknown', 'It cannot be checked that the image under the segmentation is on the mask grid (the view has not said which image it draws, or the mask is not loaded). Show the segmentation in the Standard view over its own image, then confirm.');
      case 'grid_mismatch': {
        const vals = { image: gridText(p.image), mask: gridText(p.mask) };
        return fill(t('disReview.undrawnGridMismatch', { defaultValue: 'The image under the segmentation is on another grid than the mask (image {{image}}, mask {{mask}}, columns × rows × slices): the mask is drawn sheared or cut off. Show the segmentation\'s own image (or one on its grid) under it, then confirm.', ...vals }), vals);
      }
      case 'underlay_opaque': {
        const vals = {
          layer: t(UNDERLAY_NAMES[p.layer][0], UNDERLAY_NAMES[p.layer][1]),
          pct: Math.round(p.opacity * 100), max: Math.round(MAX_UNDERLAY_OPACITY * 100),
        };
        return fill(t('disReview.undrawnUnderlayOpaque', { defaultValue: '{{layer}} is drawn under the lesions at {{pct}} %, above {{max}} %: it can hide lesions of its own colour. Hide it (the zone map: or set its opacity to {{max}} % or less), then confirm.', ...vals }), vals);
      }
      default: {
        const vals = { name: p.name, value: p.value };
        return fill(t('disReview.undrawnFaint', { defaultValue: '"{{name}}" (value {{value}}) is too faint to see.', ...vals }), vals);
      }
    }
  });
}
