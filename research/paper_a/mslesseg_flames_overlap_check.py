#!/usr/bin/env python3
"""Paper A v0.2 — is any MSLesSeg scan among the 668 FLAMeS training cases? (negative control)

FLAMeS (PMC12426979) states MSLesSeg was used only as an external TEST set. We check this against
the released nnU-Net fingerprint the same way the Ljubljana scans were identified
(ljubljana_flames_match.py): an MSLesSeg FLAIR (MNI 1 mm, brain-extracted) used for training would
appear as a fingerprint entry with spacing (1, 1, 1) and a non-zero bounding box identical to the
scan's own non-zero bounding box. Reads the public MSLesSeg release already on disk (read-only).

    python research/paper_a/mslesseg_flames_overlap_check.py <fingerprint.json> <mslesseg_root> <out_json>
"""
import glob
import json
import os
import sys

import nibabel as nib
import numpy as np


def main():
    fp_path, root, out_json = sys.argv[1:4]
    fp = json.load(open(fp_path, encoding="utf-8"))
    one = [i for i, s in enumerate(fp["spacings"]) if np.allclose(s, 1.0, atol=1e-3)]
    boxes = {tuple(int(v) for v in fp["shapes_after_crop"][i]) for i in one}
    print(f"fingerprint entries with 1 mm spacing: {len(one)} ({len(boxes)} distinct boxes)")
    rows = []
    for f in sorted(glob.glob(os.path.join(root, "**", "*_FLAIR.nii.gz"), recursive=True)):
        a = np.asarray(nib.load(f).dataobj)
        nz = np.argwhere(a != 0)
        bb = tuple(int(x) for x in (nz.max(0) - nz.min(0) + 1))
        hit = bb[::-1] in boxes
        rows.append({"scan": os.path.relpath(f, root), "bbox_nifti": list(bb), "exact_hit": bool(hit)})
    hits = [r for r in rows if r["exact_hit"]]
    print(f"MSLesSeg FLAIR scans checked: {len(rows)}; exact box matches with a 1 mm training entry: {len(hits)}")
    for r in hits:
        print("   HIT", r)
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump({"n_checked": len(rows), "n_exact_hits": len(hits), "hits": hits,
                   "n_1mm_training_entries": len(one)}, fh, indent=1)
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
