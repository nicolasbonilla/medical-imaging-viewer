/**
 * RC-016 + RC-023 — patient identity and orientation state in the viewport.
 *
 * Risk controls for HAZ-009 (wrong-patient reporting) and HAZ-006 (mirrored
 * anatomy → wrong-side reporting). Created by CAPA-004 CA-4.2.
 *
 * These tests assert what is RENDERED, never what is passed. That distinction
 * is the whole point: CAPA-004 §3.3 records that RC-016 passed verification for
 * months because `patientName={patientData?.full_name}` looked correct at the
 * call site, while ImageViewer2D destructured the prop and never rendered it.
 * A test asserting the prop was supplied would have passed too, and would have
 * been just as wrong.
 *
 * Negative control (CAPA-001 §5): remove the identity block from
 * ViewportSafetyOverlay, or stop rendering the component in ImageViewer2D, and
 * these tests MUST fail.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ViewportSafetyOverlay } from './ViewportSafetyOverlay';

describe('RC-016 — patient identity is rendered in the viewport', () => {
  it('rc016 renders the patient name as visible text, not merely accepts the prop', () => {
    render(<ViewportSafetyOverlay patientName="Ana Torres" patientMRN="MRN-99120" />);

    // getByText queries the rendered DOM. A dead prop cannot satisfy this.
    expect(screen.getByText('Ana Torres')).toBeInTheDocument();
  });

  it('rc016 renders the MRN, which was previously displayed nowhere in the viewer', () => {
    render(<ViewportSafetyOverlay patientName="Ana Torres" patientMRN="MRN-99120" />);

    expect(screen.getByText(/MRN-99120/)).toBeInTheDocument();
  });

  it('rc016 warns explicitly when identity is absent instead of rendering nothing', () => {
    // Silence would make an unidentified image indistinguishable from an
    // identified one — the failure CAPA-004 §3 describes.
    render(<ViewportSafetyOverlay />);

    expect(screen.getByTestId('viewport-identity-missing')).toBeInTheDocument();
    expect(screen.queryByTestId('viewport-patient-identity')).not.toBeInTheDocument();
  });

  it('rc016 renders identity when only the MRN is known', () => {
    render(<ViewportSafetyOverlay patientMRN="MRN-99120" />);

    expect(screen.getByTestId('viewport-patient-identity')).toBeInTheDocument();
    expect(screen.queryByTestId('viewport-identity-missing')).not.toBeInTheDocument();
  });

  it('rc016 annotation never intercepts pointer events meant for the image', () => {
    const { getByTestId } = render(<ViewportSafetyOverlay patientName="Ana Torres" />);

    // A safety annotation that blocks interaction would be removed by the next
    // developer who trips over it. It must be unobtrusive to survive.
    expect(getByTestId('viewport-safety-overlay').className).toContain('pointer-events-none');
  });
});

describe('RC-023 — orientation state is reported, never guessed', () => {
  it('rc023 displays the anatomical axis codes read from the affine', () => {
    render(<ViewportSafetyOverlay patientName="Ana Torres" anatomicalOrientation="RAS" />);

    expect(screen.getByTestId('viewport-orientation')).toHaveTextContent('RAS');
  });

  it('rc023 raises an alert when the orientation is UNKNOWN', () => {
    render(<ViewportSafetyOverlay patientName="Ana Torres" anatomicalOrientation="UNKNOWN" />);

    const warning = screen.getByTestId('viewport-orientation-unknown');
    expect(warning).toBeInTheDocument();
    expect(warning).toHaveTextContent(/left\/right cannot be verified/i);
    expect(warning).toHaveAttribute('role', 'alert');
  });

  it('rc023 treats a missing orientation exactly like UNKNOWN', () => {
    // Absent metadata must never read as "fine". Older studies, or a backend
    // that has not been redeployed, will omit the field.
    render(<ViewportSafetyOverlay patientName="Ana Torres" />);

    expect(screen.getByTestId('viewport-orientation-unknown')).toBeInTheDocument();
  });

  it('rc023 flags a non-canonical orientation as laterality-unverified', () => {
    // LAS is mirrored relative to RAS. The viewer does not canonicalise on load
    // (RC-013 open) and plane selection assumes a canonical axis order, so this
    // state must be surfaced rather than silently rendered.
    render(<ViewportSafetyOverlay patientName="Ana Torres" anatomicalOrientation="LAS" />);

    const badge = screen.getByTestId('viewport-orientation');
    expect(badge).toHaveTextContent('LAS');
    expect(badge).toHaveTextContent(/laterality unverified/i);
  });

  it('rc023 does not flag the canonical orientation as unverified', () => {
    render(<ViewportSafetyOverlay patientName="Ana Torres" anatomicalOrientation="RAS" />);

    expect(screen.getByTestId('viewport-orientation')).not.toHaveTextContent(
      /laterality unverified/i,
    );
  });

  it('rc023 never renders an L/R edge label while the axis-to-screen mapping is unverified', () => {
    // This asserts a deliberate ABSENCE, and is the most important test here.
    // An "L" drawn on the wrong edge is worse than no "L": it converts an
    // absence the clinician can see into a confident error they cannot.
    // Volumes are not canonicalised on load and imaging_service transposes with
    // fixed axis tuples that presume RAS, so no correct mapping exists yet.
    // Delete this test only together with CAPA-004 CA-4.3, and only once the
    // mapping is verified against a phantom of known laterality.
    const { container } = render(
      <ViewportSafetyOverlay patientName="Ana Torres" anatomicalOrientation="RAS" />,
    );

    const edgeLabels = Array.from(container.querySelectorAll('*')).filter((el) => {
      const text = el.textContent?.trim() ?? '';
      return el.children.length === 0 && /^[LRAPSI]$/.test(text);
    });

    expect(edgeLabels).toHaveLength(0);
  });

  it('rc023 carries a standing caveat that laterality is not labelled', () => {
    render(<ViewportSafetyOverlay patientName="Ana Torres" anatomicalOrientation="RAS" />);

    expect(screen.getByText(/confirm side against the source study/i)).toBeInTheDocument();
  });
});

describe('the overlay is wired into the viewer, not merely available', () => {
  /**
   * A component that works in isolation but is never mounted is exactly the
   * defect CAPA-004 §3 found: `patientName` reached ImageViewer2D and was
   * discarded. The tests above prove the component renders correctly; these
   * prove the viewer actually uses it.
   *
   * These are STATIC source checks, and they are deliberately labelled as such.
   * Rendering ImageViewer2D requires canvas, Zustand stores, React Query and a
   * loaded series — a render test would be brittle enough to get deleted, and a
   * deleted guard protects nothing. A source assertion is weaker evidence but
   * it is honest about what it is, and it fails loudly if the wiring is cut.
   */
  const viewerSource = readFileSync(
    join(__dirname, 'ImageViewer2D.tsx'),
    'utf-8',
  );

  it('rc016 ImageViewer2D renders ViewportSafetyOverlay', () => {
    expect(viewerSource).toContain('<ViewportSafetyOverlay');
  });

  it('rc016 ImageViewer2D passes patient identity to the overlay', () => {
    expect(viewerSource).toMatch(/patientName=\{patientName\}/);
    expect(viewerSource).toMatch(/patientMRN=\{patientMRN\}/);
  });

  it('rc023 ImageViewer2D passes the anatomical orientation to the overlay', () => {
    expect(viewerSource).toMatch(/anatomicalOrientation=\{/);
  });

  it('rc016 the overlay is not rendered behind a conditional', () => {
    // A safety annotation shown only in some states is not a safety annotation.
    // Guard against a future `{showOverlay && <ViewportSafetyOverlay ...`.
    const conditional = /[&?]\s*\n?\s*<ViewportSafetyOverlay/;
    expect(viewerSource).not.toMatch(conditional);
  });
});
