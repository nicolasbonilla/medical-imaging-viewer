"""
Download the MSMask atlas from LST-AI v1.1.0 release.

The MSMask is a manually-labeled MNI152 atlas used by LST-AI for MAGNIMS
zone classification (Wiltgen et al., NeuroImage: Clinical 2024).

Labels: CSF=1, GM=2, WM=3, Ventricles=4, Infratentorial=5

Only extracts the atlas file (~5MB) from the 388MB lst_data.zip.
"""

import io
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

LST_AI_RELEASE_URL = (
    "https://github.com/CompImg/LST-AI/releases/download/v1.1.0/lst_data.zip"
)
ATLAS_PATH_IN_ZIP = "atlas/sub-mni152_space-mni_msmask.nii.gz"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "backend" / "data" / "msmask"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "sub-mni152_space-mni_msmask.nii.gz"

    if output_file.exists():
        print(f"MSMask already exists: {output_file}")
        print(f"Size: {output_file.stat().st_size:,} bytes")
        return

    print(f"Downloading lst_data.zip from LST-AI v1.1.0 release...")
    print(f"URL: {LST_AI_RELEASE_URL}")
    print("(388 MB — this may take a few minutes)")

    response = urlopen(LST_AI_RELEASE_URL)
    zip_bytes = response.read()
    print(f"Downloaded {len(zip_bytes):,} bytes")

    print(f"Extracting {ATLAS_PATH_IN_ZIP}...")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # List atlas-related files for reference
        atlas_files = [n for n in zf.namelist() if "atlas" in n.lower() or "msmask" in n.lower()]
        if atlas_files:
            print(f"Atlas files in zip: {atlas_files}")

        if ATLAS_PATH_IN_ZIP not in zf.namelist():
            # Try to find it with different prefix
            candidates = [n for n in zf.namelist() if "msmask" in n.lower()]
            if candidates:
                print(f"Exact path not found, but found: {candidates}")
                actual_path = candidates[0]
            else:
                print(f"ERROR: {ATLAS_PATH_IN_ZIP} not found in zip")
                print(f"Zip contents (first 30): {zf.namelist()[:30]}")
                sys.exit(1)
        else:
            actual_path = ATLAS_PATH_IN_ZIP

        data = zf.read(actual_path)
        output_file.write_bytes(data)
        print(f"Saved: {output_file} ({len(data):,} bytes)")

    # Verify
    try:
        import nibabel as nib
        import numpy as np
        img = nib.load(str(output_file))
        mask = np.asarray(img.dataobj)
        unique = sorted(set(mask.flat))
        print(f"\nVerification:")
        print(f"  Shape: {img.shape}")
        print(f"  Affine diagonal: {list(np.diag(img.affine[:3,:3]))}")
        print(f"  Origin: {list(img.affine[:3,3])}")
        print(f"  Unique labels: {unique}")
        print(f"  Expected: [0, 1(CSF), 2(GM), 3(WM), 4(Ventricles), 5(Infratentorial)]")
    except ImportError:
        print("(nibabel not installed — skipping verification)")


if __name__ == "__main__":
    main()
