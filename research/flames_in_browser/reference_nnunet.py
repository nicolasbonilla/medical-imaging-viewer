"""Reference FLAMeS segmentation with nnU-Net v2's OWN predictor (CPU), for the browser parity harness.

    python -I reference_nnunet.py <trainer folder> <FLAIR.nii.gz> <out.nii.gz> --backend torch|onnx
                                  [--onnx flames-fold0.onnx] [--fold 0] [--mirror] [--threads 8]

backend torch : nnUNetPredictor + the PyTorch checkpoint (fold_<fold>/checkpoint_final.pth).
                This is exactly `nnUNetv2_predict -d 004 -c 3d_fullres -tr nnUNetTrainer_8000epochs -f <fold>`
                (add --mirror for the default test-time mirroring, omit it for --disable_tta).
backend onnx  : the same nnUNetPredictor (same preprocessing, sliding window, float16 accumulation,
                resampling and export code) but the network is the ONNX graph shipped to the browser,
                run by native ONNX Runtime. Isolates the effect of the ONNX conversion (float16 weight storage).

Comparing the browser (TypeScript + ONNX Runtime Web) mask with the 'onnx' reference isolates the
port itself; comparing with the 'torch' reference gives the end-to-end deviation from nnU-Net.
"""
import argparse, json, os, sys, time, tempfile, shutil

import numpy as np
import torch

os.environ.setdefault('nnUNet_raw', tempfile.gettempdir())
os.environ.setdefault('nnUNet_preprocessed', tempfile.gettempdir())
os.environ.setdefault('nnUNet_results', tempfile.gettempdir())

from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor  # noqa: E402
from nnunetv2.utilities.plans_handling.plans_handler import PlansManager  # noqa: E402
from batchgenerators.utilities.file_and_folder_operations import load_json  # noqa: E402


class OrtNetwork(torch.nn.Module):
    """Drop-in for the nnU-Net network: forward() runs the ONNX graph with native ONNX Runtime."""

    def __init__(self, path, threads):
        super().__init__()
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.enable_cpu_mem_arena = False
        self.session = ort.InferenceSession(path, so, providers=['CPUExecutionProvider'])

    def forward(self, x):
        y = self.session.run(None, {'input': x.detach().cpu().numpy().astype(np.float32)})[0]
        return torch.from_numpy(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('model_folder')
    ap.add_argument('flair')
    ap.add_argument('out')
    ap.add_argument('--backend', choices=['torch', 'onnx'], required=True)
    ap.add_argument('--onnx')
    ap.add_argument('--fold', type=int, default=0)
    ap.add_argument('--mirror', action='store_true')
    ap.add_argument('--threads', type=int, default=8)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    predictor = nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=a.mirror,
                                perform_everything_on_device=False, device=torch.device('cpu'),
                                verbose=False, verbose_preprocessing=False, allow_tqdm=False)
    if a.backend == 'torch':
        predictor.initialize_from_trained_model_folder(a.model_folder, use_folds=(a.fold,), checkpoint_name='checkpoint_final.pth')
    else:
        plans_manager = PlansManager(load_json(os.path.join(a.model_folder, 'plans.json')))
        dataset_json = load_json(os.path.join(a.model_folder, 'dataset.json'))
        configuration_manager = plans_manager.get_configuration('3d_fullres')
        predictor.manual_initialization(OrtNetwork(a.onnx, a.threads), plans_manager, configuration_manager, [{}],
                                        dataset_json, 'nnUNetTrainer_8000epochs', (0, 1, 2))
    work = tempfile.mkdtemp(prefix='flames_ref_')
    try:
        started = time.time()
        predictor.predict_from_files_sequential([[a.flair]], [os.path.join(work, 'case')], save_probabilities=False,
                                                overwrite=True)
        seconds = time.time() - started
        produced = os.path.join(work, 'case.nii.gz')
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        shutil.move(produced, a.out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    meta = {'backend': a.backend, 'fold': a.fold, 'mirror': a.mirror, 'seconds': round(seconds, 1),
            'threads': a.threads, 'flair': os.path.basename(a.flair), 'onnx': os.path.basename(a.onnx) if a.onnx else None}
    with open(a.out + '.json', 'w') as f:
        json.dump(meta, f, indent=1)
    print(json.dumps(meta))


if __name__ == '__main__':
    main()
