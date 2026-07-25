/**
 * ViewportSafetyOverlay — patient identity and orientation state, burned into
 * the image viewport itself.
 *
 * Risk controls RC-016 (patient identification) and RC-023 (anatomical
 * orientation), for HAZ-009 and HAZ-006. Created by CAPA-004 CA-4.2.
 *
 * WHY THIS EXISTS
 * CAPA-004 §3 found that no patient identifier was rendered in the image
 * viewport in any view mode. `patientName` was passed into ImageViewer2D and
 * never rendered — a dead prop — and MRN was displayed nowhere in the viewer.
 * Identity appeared only as a page breadcrumb, which is absent from a
 * screenshot, an exported slice, or a maximised viewport. Conventional DICOM
 * viewers guard this with a persistent burned-in corner annotation; this is
 * that annotation.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO — read before adding L/R edge markers
 * It does not draw L/R/A/P/S/I labels on the viewport edges, even though that
 * is the obvious next step and CA-4.2 asks for it. Drawing them requires
 * knowing how volume axes map to screen edges, and that mapping is currently
 * NOT established:
 *
 *   - Volumes are not canonicalised on load (RC-013 remains open; see
 *     nifti_utils.py for why that migration must move image and mask together).
 *   - Plane selection in imaging_service transposes with fixed axis tuples —
 *     (2,1,0) for sagittal, (0,2,1) for coronal — which presume a canonical
 *     axis order that is never enforced. For a non-RAS volume, the plane
 *     labelled "sagittal" is not necessarily sagittal.
 *
 * An "L" drawn on the wrong edge is materially worse than no "L": it converts
 * an absence the clinician can see into a confident error they cannot. So this
 * component reports the orientation as a FACT read from the affine, warns when
 * it is unknown or non-canonical, and leaves the edges unlabelled until the
 * axis→screen mapping is verified against a phantom of known laterality.
 * That verification is CAPA-004 CA-4.3.
 */
import { useTranslation } from 'react-i18next';

interface ViewportSafetyOverlayProps {
  patientName?: string;
  patientMRN?: string;
  studyDescription?: string;
  /** Axis codes from the NIfTI affine, e.g. "RAS". "UNKNOWN" when indeterminate. */
  anatomicalOrientation?: string;
}

const CANONICAL_ORIENTATION = 'RAS';

export function ViewportSafetyOverlay({
  patientName,
  patientMRN,
  studyDescription,
  anatomicalOrientation,
}: ViewportSafetyOverlayProps) {
  const { t } = useTranslation();

  // Absent identity is itself a safety-relevant state and must be visible.
  // Rendering nothing would make an unidentified image look the same as an
  // identified one — the failure CAPA-004 §3 describes.
  const hasIdentity = Boolean(patientName || patientMRN);

  const orientationKnown =
    Boolean(anatomicalOrientation) && anatomicalOrientation !== 'UNKNOWN';
  const orientationCanonical = anatomicalOrientation === CANONICAL_ORIENTATION;

  return (
    // pointer-events-none: this must never intercept a click intended for the
    // image. It is an annotation, not a control.
    <div
      className="pointer-events-none absolute inset-0 z-20 select-none"
      data-testid="viewport-safety-overlay"
    >
      {/* Patient identity — top left, the DICOM convention */}
      <div className="absolute top-2 left-2 max-w-[60%]">
        {hasIdentity ? (
          <div
            className="rounded bg-black/60 px-2 py-1 text-[11px] leading-tight text-gray-100 backdrop-blur-sm"
            data-testid="viewport-patient-identity"
          >
            {patientName && (
              <div className="font-semibold tracking-wide">{patientName}</div>
            )}
            {patientMRN && (
              <div className="text-gray-300">
                {t('viewer.mrn', 'MRN')}: {patientMRN}
              </div>
            )}
            {studyDescription && (
              <div className="truncate text-gray-400">{studyDescription}</div>
            )}
          </div>
        ) : (
          <div
            className="rounded bg-amber-500/20 px-2 py-1 text-[11px] font-semibold text-amber-200 ring-1 ring-amber-400/50"
            data-testid="viewport-identity-missing"
            role="status"
          >
            {t(
              'viewer.patientUnidentified',
              'PATIENT NOT IDENTIFIED — do not use for reporting',
            )}
          </div>
        )}
      </div>

      {/* Orientation state — top right */}
      <div className="absolute top-2 right-2">
        {orientationKnown ? (
          <div
            className={
              orientationCanonical
                ? 'rounded bg-black/60 px-2 py-1 text-[11px] text-gray-300 backdrop-blur-sm'
                : 'rounded bg-amber-500/20 px-2 py-1 text-[11px] font-semibold text-amber-200 ring-1 ring-amber-400/50'
            }
            data-testid="viewport-orientation"
            title={t(
              'viewer.orientationTitle',
              'Anatomical axis codes read from the image affine',
            )}
          >
            {anatomicalOrientation}
            {!orientationCanonical && (
              <span className="ml-1 font-normal">
                {t('viewer.orientationNonCanonical', '— not RAS; laterality unverified')}
              </span>
            )}
          </div>
        ) : (
          <div
            className="rounded bg-red-500/25 px-2 py-1 text-[11px] font-semibold text-red-200 ring-1 ring-red-400/60"
            data-testid="viewport-orientation-unknown"
            role="alert"
          >
            {t(
              'viewer.orientationUnknown',
              'ORIENTATION UNKNOWN — left/right cannot be verified',
            )}
          </div>
        )}
      </div>

      {/* Standing caveat, bottom. Present in every view because the axis→screen
          mapping is unverified for every view. Remove only when CA-4.3 closes. */}
      <div className="absolute bottom-2 left-1/2 -translate-x-1/2">
        <div className="rounded bg-black/50 px-2 py-0.5 text-[10px] text-gray-400 backdrop-blur-sm">
          {t(
            'viewer.lateralityNotLabelled',
            'Laterality not labelled — confirm side against the source study',
          )}
        </div>
      </div>
    </div>
  );
}

export default ViewportSafetyOverlay;
