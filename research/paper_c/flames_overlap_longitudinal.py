#!/usr/bin/env python3
"""Paper C — did FLAMeS train on the open_ms_data LONGITUDINAL scans (Lesjak et al. 2016)?

Evidence (public, small):
  * the nnU-Net `dataset_fingerprint.json` shipped inside the released FLAMeS weights (Zenodo
    17955359; fetched with HTTP range requests by research/paper_a/flames_zip_inspect.py on branch
    research/paper-a-v0.3): original voxel spacing and post-crop shape of all 668 training cases;
  * the NIfTI headers of the 40 longitudinal RAW FLAIRs (study1/study2 x 20 patients), read with
    an HTTP range request (first 4 kB; no image body is downloaded).

Logic: a training case can only be one of these scans if its ORIGINAL spacing equals the scan's
spacing (nnU-Net records the spacing of the image it was given). If no fingerprint entry has the
spacing of any longitudinal raw FLAIR (to 0.002 mm, any axis order), the longitudinal scans
were not given to FLAMeS in their raw geometry. They could still have entered resampled (e.g. to
MNI 1 mm); we report how many fingerprint entries are 1 mm isotropic as the residual
uncertainty, and we also check the cross-sectional match (paper A v0.2) for context.

    python -I research/paper_c/flames_overlap_longitudinal.py <dataset_fingerprint.json> <out_json>
"""
import json
import struct
import sys
import urllib.request
import zlib

RAW = "https://raw.githubusercontent.com/muschellij2/open_ms_data/master/longitudinal/raw"


def header(url):
    req = urllib.request.Request(url, headers={"Range": "bytes=0-4095"})
    with urllib.request.urlopen(req, timeout=120) as r:
        gz = r.read()
    d = zlib.decompressobj(31).decompress(gz)
    h = d[:348]
    dim = struct.unpack("<8h", h[40:56])
    pix = struct.unpack("<8f", h[76:108])
    n = dim[0]
    return [int(x) for x in dim[1:1 + n]], [round(float(x), 4) for x in pix[1:1 + n]]


def same_spacing(a, b, tol=0.002):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(sorted(a), sorted(b)))


def main():
    fp_path, out_json = sys.argv[1:3]
    fp = json.load(open(fp_path))
    spacings = fp["spacings"]
    shapes = fp["shapes_after_crop"]
    rec = {"n_fingerprint_entries": len(spacings), "scans": {}, "matches": []}
    iso1 = sum(1 for s in spacings if all(abs(x - 1.0) <= 0.002 for x in s))
    rec["n_fingerprint_entries_1mm_iso"] = iso1
    for p in range(1, 21):
        for st in (1, 2):
            dims, pix = header(f"{RAW}/patient{p:02d}/study{st}_FLAIR.nii.gz")
            key = f"patient{p:02d}_study{st}"
            hits = [i for i, s in enumerate(spacings) if same_spacing(s, pix[:3])]
            rec["scans"][key] = {"dims": dims, "pixdim": pix, "fingerprint_hits": hits,
                                 "hit_shapes_after_crop": [shapes[i] for i in hits]}
            print(f"{key}: dims {dims} pixdim {pix} -> fingerprint entries with this spacing: {hits}")
            if hits:
                rec["matches"].append(key)
    distinct = sorted({tuple(v["pixdim"][:3]) for v in rec["scans"].values()})
    rec["distinct_raw_spacings"] = [list(x) for x in distinct]
    rec["verdict"] = ("no fingerprint entry has the raw spacing of any longitudinal FLAIR"
                      if not rec["matches"] else "SOME longitudinal FLAIR spacings occur in the fingerprint")
    print("distinct raw spacings:", distinct)
    print("fingerprint entries at 1 mm isotropic (residual uncertainty: resampled inputs):", iso1)
    print("VERDICT:", rec["verdict"])
    json.dump(rec, open(out_json, "w"), indent=1)
    print("wrote", out_json)


if __name__ == "__main__":
    main()
