"""
LST-AI HTTP Wrapper.

Thin Flask server that wraps the LST-AI command-line tool,
exposing it as an HTTP service for the medical imaging viewer backend.

LST-AI: Wiltgen et al., NeuroImage: Clinical 2024, 42, 103611
"""

import os
import subprocess
import time
import logging
from pathlib import Path

from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lst-ai-server")

LST_AI_VERSION = "1.0.3"


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "tool": "lst-ai",
        "version": LST_AI_VERSION,
        "citation": (
            "Wiltgen T, et al. LST-AI: a deep learning ensemble for "
            "accurate MS lesion segmentation. NeuroImage: Clinical 2024;42:103611."
        ),
    })


@app.route("/info", methods=["GET"])
def info():
    """Tool information endpoint."""
    return jsonify({
        "id": "lst-ai",
        "name": "LST-AI",
        "version": LST_AI_VERSION,
        "description": (
            "Automated MS lesion segmentation using 3x 3D U-Net ensemble "
            "with test-time augmentation. Includes MAGNIMS 2021 zone classification."
        ),
        "required_inputs": ["T1w", "FLAIR"],
        "outputs": {
            "lesion_mask": "Binary lesion mask (NIfTI)",
            "lesion_types": "MAGNIMS zone-classified lesion mask (PV=1, JC=2, IT=3, DWM=4)",
        },
        "license": "Open-source research",
        "fda_status": "research_only",
    })


@app.route("/segment", methods=["POST"])
def segment():
    """
    Run LST-AI lesion segmentation.

    Expects JSON:
    {
        "t1_path": "/shared/<task_id>/t1.nii.gz",
        "flair_path": "/shared/<task_id>/flair.nii.gz",
        "output_dir": "/shared/<task_id>/output"
    }

    Returns JSON with output file paths.
    """
    data = request.get_json()
    t1_path = data.get("t1_path")
    flair_path = data.get("flair_path")
    output_dir = data.get("output_dir")

    if not all([t1_path, flair_path, output_dir]):
        return jsonify({"error": "Missing required fields: t1_path, flair_path, output_dir"}), 400

    # Validate input files exist
    for path, name in [(t1_path, "T1"), (flair_path, "FLAIR")]:
        if not Path(path).exists():
            return jsonify({"error": f"{name} file not found: {path}"}), 404

    os.makedirs(output_dir, exist_ok=True)

    start_time = time.time()

    try:
        # Run LST-AI command
        # LST-AI CLI: lst --t1 <t1> --flair <flair> --output <output_dir>
        cmd = [
            "lst",
            "--t1", t1_path,
            "--flair", flair_path,
            "--output", output_dir,
            "--temp", os.path.join(output_dir, "temp"),
        ]

        logger.info(f"Running LST-AI: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min timeout
        )

        elapsed = time.time() - start_time

        if result.returncode != 0:
            logger.error(f"LST-AI failed: {result.stderr}")
            return jsonify({
                "error": f"LST-AI exited with code {result.returncode}",
                "stderr": result.stderr[-1000:] if result.stderr else "",
                "elapsed_seconds": elapsed,
            }), 500

        # Find output files
        output_path = Path(output_dir)
        lesion_masks = list(output_path.glob("*lesion_mask*")) + list(output_path.glob("*ples*"))
        lesion_types = list(output_path.glob("*lesion_types*")) + list(output_path.glob("*zone*"))

        lesion_mask_name = lesion_masks[0].name if lesion_masks else "lesion_mask.nii.gz"
        lesion_types_name = lesion_types[0].name if lesion_types else "lesion_types.nii.gz"

        logger.info(f"LST-AI completed in {elapsed:.1f}s")

        return jsonify({
            "status": "completed",
            "lesion_mask": lesion_mask_name,
            "lesion_types": lesion_types_name,
            "elapsed_seconds": elapsed,
            "validation_source": f"lst-ai-v{LST_AI_VERSION}",
        })

    except subprocess.TimeoutExpired:
        return jsonify({"error": "LST-AI timed out (>15 minutes)"}), 504
    except Exception as e:
        logger.error(f"LST-AI error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
