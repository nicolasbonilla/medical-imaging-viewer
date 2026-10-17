// @vitest-environment node
/**
 * Header evidence for the FLAIR gate (RC-049): the NIfTI reader exposes descrip / aux_file / intent_name,
 * text found in NIfTI extensions, and DICOM attributes from a DICOM extension (ecode 2).
 */
import { describe, expect, it } from 'vitest';
import { parseNifti } from '../nifti';
import { headerContrastEvidence } from '../headerEvidence';

function ascii(view: Uint8Array, offset: number, text: string) {
  for (let i = 0; i < text.length; i++) view[offset + i] = text.charCodeAt(i);
}

/** Explicit-VR little-endian DICOM element (short VR form). */
function dicomElement(group: number, element: number, vr: string, value: string): Uint8Array {
  const v = value.length % 2 ? value + ' ' : value;
  const out = new Uint8Array(8 + v.length);
  const dv = new DataView(out.buffer);
  dv.setUint16(0, group, true);
  dv.setUint16(2, element, true);
  ascii(out, 4, vr);
  dv.setUint16(6, v.length, true);
  ascii(out, 8, v);
  return out;
}

function niftiWith(descrip: string, extensions: { code: number; payload: Uint8Array }[]): Uint8Array {
  const extBytes = extensions.map((e) => {
    const size = Math.ceil((8 + e.payload.length) / 16) * 16;
    const b = new Uint8Array(size);
    const dv = new DataView(b.buffer);
    dv.setInt32(0, size, true);
    dv.setInt32(4, e.code, true);
    b.set(e.payload, 8);
    return b;
  });
  const extTotal = extBytes.reduce((s, b) => s + b.length, 0);
  const voxOffset = 352 + extTotal;
  const dims = [2, 2, 2];
  const buf = new Uint8Array(voxOffset + 8 * 4);
  const dv = new DataView(buf.buffer);
  dv.setInt32(0, 348, true);
  dv.setInt16(40, 3, true);
  dims.forEach((d, i) => dv.setInt16(42 + 2 * i, d, true));
  dv.setInt16(48, 1, true);
  dv.setInt16(70, 16, true); // float32
  dv.setInt16(72, 32, true);
  [1, 1, 1, 1].forEach((p, i) => dv.setFloat32(76 + 4 * i, p, true));
  dv.setFloat32(108, voxOffset, true);
  dv.setFloat32(112, 1, true);
  ascii(buf, 148, descrip);
  ascii(buf, 344, 'n+1\0');
  buf[348] = extensions.length ? 1 : 0;
  let o = 352;
  for (const b of extBytes) {
    buf.set(b, o);
    o += b.length;
  }
  return buf;
}

describe('NIfTI header evidence', () => {
  it('rc049 exposes descrip and extension text', () => {
    const v = parseNifti(niftiWith('TE=81;Time=101112.000', [{ code: 6, payload: new TextEncoder().encode('Sag 3D MPRAGE') }]));
    expect(v.headerText).toContain('TE=81;Time=101112.000');
    expect(v.headerText.join(' ')).toContain('Sag 3D MPRAGE');
    expect(headerContrastEvidence(v.headerText, v.dicom, null).verdict).toBe('contradicts');
  });

  it('rc049 reads InversionTime and SeriesDescription from a DICOM extension', () => {
    const payload = new Uint8Array([
      ...dicomElement(0x0008, 0x103e, 'LO', 'AX T2 FLAIR'),
      ...dicomElement(0x0018, 0x0082, 'DS', '2500'),
    ]);
    const v = parseNifti(niftiWith('', [{ code: 2, payload }]));
    expect(v.dicom.inversionTimeMs).toBe(2500);
    expect(v.dicom.seriesDescription).toBe('AX T2 FLAIR');
    expect(headerContrastEvidence(v.headerText, v.dicom, null).verdict).toBe('supports');
  });

  it('rc049 a short inversion time in the DICOM extension contradicts FLAIR', () => {
    const v = parseNifti(niftiWith('', [{ code: 2, payload: dicomElement(0x0018, 0x0082, 'DS', '900') }]));
    expect(headerContrastEvidence(v.headerText, v.dicom, null).verdict).toBe('contradicts');
  });

  it('rc049 no header text => no evidence either way', () => {
    const v = parseNifti(niftiWith('', []));
    expect(headerContrastEvidence(v.headerText, v.dicom, null).verdict).toBe('none');
  });
});
