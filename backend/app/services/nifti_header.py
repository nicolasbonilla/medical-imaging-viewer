"""The ONE NIfTI header reader of the app (fifteenth review of PR #81, S6): the size and byte order of a NIfTI-1 / NIfTI-2
header and the decompressed start of a (gzip) NIfTI — the header with every extension, up to vox_offset — shared by the
quality gate's header reader and SegmentationService.nifti_header_grid (PRB-030 / RC-092, the 3D realignment). Never the
voxels. DRAFT, PENDING owner approval."""
import math
import struct
import zlib
from typing import Optional, Tuple

DECOMPRESSED_MAX = 16 * 1024 * 1024        # O1 (twelfth review): a header with its extensions, at most 16 MiB
_FIRST = 1 << 20                           # read when vox_offset cannot be read


def sizeof_hdr(raw: bytes) -> Tuple[Optional[int], Optional[str]]:
    """(348 or 540, '<' or '>') of a NIfTI-1 / NIfTI-2 header, else (None, None)."""
    if len(raw) < 4:
        return None, None
    for endian in ("<", ">"):
        size = struct.unpack(endian + "i", raw[:4])[0]
        if size in (348, 540):
            return size, endian
    return None, None


def vox_offset(raw: bytes) -> Optional[float]:
    """The header's vox_offset (where the voxels start), or None when it cannot be read."""
    size, endian = sizeof_hdr(raw)
    if size is None or len(raw) < (112 if size == 348 else 176):
        return None
    vox = (struct.unpack(endian + "f", raw[108:112])[0] if size == 348
           else struct.unpack(endian + "q", raw[168:176])[0])
    return float(vox) if isinstance(vox, (int, float)) and math.isfinite(vox) and vox > 0 else None


def header_prefix(data: bytes) -> bytes:
    """The decompressed start of a NIfTI: an uncompressed file as it is; a gzip one decompressed up to vox_offset (the
    header and every extension), at most DECOMPRESSED_MAX; b"" when the gzip stream is broken."""
    if data[:2] != b"\x1f\x8b":
        return data
    try:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        head = d.decompress(data, 544)
        size, _endian = sizeof_hdr(head)
        want = _FIRST
        vox = vox_offset(head) if size else None
        if vox is not None:
            want = int(min(max(vox, size + 4), DECOMPRESSED_MAX))
        rest = d.decompress(d.unconsumed_tail, want - len(head)) if want > len(head) else b""
        return head + rest
    except (zlib.error, struct.error, ValueError):
        return b""
