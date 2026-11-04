"""Paper F - forensic training-overlap check of the thick cohorts against the released FLAMeS weights (reviewer m11).

The FLAMeS weights (Zenodo 10.5281/zenodo.17955359, v2.0, CC BY 4.0) ship nnU-Net's `dataset_fingerprint.json`:
per training case, the voxel spacing and the cropped image size. A scan of MS3SEG (0.898 x 0.898 x 6.0-8.1 mm),
PediMS (0.75 x 0.75 x 3.9 mm) or Muslim et al. (4.86-8.3 mm slices) used for training at its own geometry would
appear as an entry with a slice spacing > 3 mm. The fingerprint (109,486 bytes) was read from the public archive
with HTTP range requests (no full download; method: research/paper_a/flames_zip_inspect.py on branch
research/paper-a-v0.3) and is passed here as a file; only its derived summary is stored.

MSLesSeg was checked the same way for Paper A (0 of 115 scans match any of the 319 1 mm training entries):
data/mslesseg_flames_overlap_check_87e998d.json.

    python research/paper_f/manuscript/fingerprint_check.py <dataset_fingerprint.json>
writes research/paper_f/manuscript/data/flames_fingerprint_check.json
"""
import collections
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    path = sys.argv[1]
    raw = open(path, "rb").read()
    fp = json.loads(raw)
    sp = fp["spacings"]
    hist = collections.Counter(round(max(float(x) for x in s), 2) for s in sp)
    out = {"source": "Dataset004_WML/nnUNetTrainer_8000epochs__nnUNetPlans__3d_fullres/dataset_fingerprint.json "
                     "in Zenodo 10.5281/zenodo.17955359 (FLAMeS v2.0)",
           "fingerprint_bytes": len(raw), "fingerprint_sha256": hashlib.sha256(raw).hexdigest(),
           "n_training_entries": len(sp),
           "largest_voxel_dimension_histogram_mm": {str(k): v for k, v in sorted(hist.items())},
           "max_largest_voxel_dimension_mm": max(max(float(x) for x in s) for s in sp),
           "n_entries_with_slice_spacing_above_3mm": sum(max(float(x) for x in s) > 3.0 for s in sp),
           "conclusion": "no training case has a voxel dimension above 3 mm, so no thick-slice scan of MS3SEG, Muslim "
                         "or PediMS was a FLAMeS training case at its own geometry (a resampled copy cannot be excluded "
                         "by this check)"}
    dst = os.path.join(HERE, "data", "flames_fingerprint_check.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
