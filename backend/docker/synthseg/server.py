"""
SynthSeg HTTP Wrapper.

Thin Flask server that wraps SynthSeg brain parcellation,
exposing it as an HTTP service for the medical imaging viewer backend.

SynthSeg: Billot et al., Medical Image Analysis 2023, 83, 102789
"""

import os
import subprocess
import time
import logging
from pathlib import Path

from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("synthseg-server")

SYNTHSEG_VERSION = "2.0"


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "tool": "synthseg",
        "version": SYNTHSEG_VERSION,
        "citation": (
            "Billot B, et al. SynthSeg: Segmentation of brain MRI scans of any "
            "contrast and resolution without retraining. "
            "Medical Image Analysis 2023;83:102789."
        ),
    })


@app.route("/info", methods=["GET"])
def info():
    """Tool information endpoint."""
    return jsonify({
        "id": "synthseg",
        "name": "SynthSeg",
        "version": SYNTHSEG_VERSION,
        "description": (
            "Contrast-agnostic brain parcellation of 30+ structures. "
            "Works on any MRI contrast (T1, T2, FLAIR, etc.). "
            "Part of FreeSurfer 7.4+."
        ),
        "required_inputs": ["Any MRI"],
        "outputs": {
            "parcellation": "Brain parcellation mask with FreeSurfer labels (NIfTI)",
            "volumes": "Per-structure volume measurements (CSV)",
            "qc": "Quality control scores (CSV)",
        },
        "license": "FreeSurfer License",
        "fda_status": "research_only",
    })


@app.route("/parcellate", methods=["POST"])
def parcellate():
    """
    Run SynthSeg brain parcellation.

    Expects JSON:
    {
        "input_path": "/shared/<task_id>/input.nii.gz",
        "output_dir": "/shared/<task_id>/output"
    }

    Returns JSON with output file paths.
    """
    data = request.get_json()
    input_path = data.get("input_path")
    output_dir = data.get("output_dir")

    if not all([input_path, output_dir]):
        return jsonify({"error": "Missing required fields: input_path, output_dir"}), 400

    if not Path(input_path).exists():
        return jsonify({"error": f"Input file not found: {input_path}"}), 404

    os.makedirs(output_dir, exist_ok=True)

    start_time = time.time()

    parcellation_path = os.path.join(output_dir, "synthseg.nii.gz")
    volumes_path = os.path.join(output_dir, "volumes.csv")
    qc_path = os.path.join(output_dir, "qc.csv")

    try:
        # Try SynthSeg Python API first
        try:
            from SynthSeg.predict import predict as synthseg_predict

            synthseg_predict(
                path_images=input_path,
                path_segmentations=parcellation_path,
                path_volumes=volumes_path,
                path_qc=qc_path,
            )

        except ImportError:
            # Fallback to CLI
            cmd = [
                "mri_synthseg",
                "--i", input_path,
                "--o", parcellation_path,
                "--vol", volumes_path,
                "--qc", qc_path,
                "--cpu",  # CPU mode for compatibility
            ]

            logger.info(f"Running SynthSeg CLI: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout
            )

            if result.returncode != 0:
                logger.error(f"SynthSeg failed: {result.stderr}")
                return jsonify({
                    "error": f"SynthSeg exited with code {result.returncode}",
                    "stderr": result.stderr[-1000:] if result.stderr else "",
                }), 500

        elapsed = time.time() - start_time
        logger.info(f"SynthSeg completed in {elapsed:.1f}s")

        response = {
            "status": "completed",
            "parcellation": "synthseg.nii.gz",
            "elapsed_seconds": elapsed,
            "validation_source": f"synthseg-v{SYNTHSEG_VERSION}",
        }

        if Path(volumes_path).exists():
            response["volumes"] = "volumes.csv"
        if Path(qc_path).exists():
            response["qc"] = "qc.csv"

        return jsonify(response)

    except subprocess.TimeoutExpired:
        return jsonify({"error": "SynthSeg timed out (>5 minutes)"}), 504
    except Exception as e:
        logger.error(f"SynthSeg error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/volumetry", methods=["POST"])
def volumetry():
    """
    Compute volumetry from an existing SynthSeg parcellation.

    Expects JSON:
    {
        "parcellation_path": "/shared/<task_id>/synthseg.nii.gz"
    }
    """
    data = request.get_json()
    parcellation_path = data.get("parcellation_path")

    if not parcellation_path or not Path(parcellation_path).exists():
        return jsonify({"error": "Parcellation file not found"}), 404

    try:
        import nibabel as nib
        import numpy as np

        img = nib.load(parcellation_path)
        parcellation = np.asarray(img.dataobj)
        voxel_sizes = img.header.get_zooms()[:3]
        voxel_volume_mm3 = float(np.prod(voxel_sizes))

        # FreeSurfer label names
        label_names = {
            2: "Left Cerebral WM", 3: "Left Cerebral Cortex",
            4: "Left Lateral Ventricle", 5: "Left Inf Lat Ventricle",
            7: "Left Cerebellum WM", 8: "Left Cerebellum Cortex",
            10: "Left Thalamus", 11: "Left Caudate",
            12: "Left Putamen", 13: "Left Pallidum",
            14: "3rd Ventricle", 15: "4th Ventricle",
            16: "Brain Stem", 17: "Left Hippocampus",
            18: "Left Amygdala", 24: "CSF",
            26: "Left Accumbens", 28: "Left VentralDC",
            41: "Right Cerebral WM", 42: "Right Cerebral Cortex",
            43: "Right Lateral Ventricle", 44: "Right Inf Lat Ventricle",
            46: "Right Cerebellum WM", 47: "Right Cerebellum Cortex",
            49: "Right Thalamus", 50: "Right Caudate",
            51: "Right Putamen", 52: "Right Pallidum",
            53: "Right Hippocampus", 54: "Right Amygdala",
            58: "Right Accumbens", 60: "Right VentralDC",
        }

        volumes = []
        unique_labels = np.unique(parcellation)

        for label_id in unique_labels:
            if label_id == 0:
                continue
            count = int(np.sum(parcellation == label_id))
            volume_mm3 = count * voxel_volume_mm3
            volumes.append({
                "label_id": int(label_id),
                "structure_name": label_names.get(int(label_id), f"Label {label_id}"),
                "voxel_count": count,
                "volume_mm3": round(volume_mm3, 2),
                "volume_ml": round(volume_mm3 / 1000.0, 4),
            })

        return jsonify({
            "status": "completed",
            "voxel_volume_mm3": round(voxel_volume_mm3, 4),
            "structures": volumes,
            "total_structures": len(volumes),
        })

    except Exception as e:
        logger.error(f"Volumetry error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
