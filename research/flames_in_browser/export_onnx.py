"""Export one FLAMeS fold (nnU-Net v2 checkpoint, Zenodo 17955359 v2.0) to a browser-ready ONNX graph.

    python -I export_onnx.py <trainer folder> <fold> <out.onnx> [--manifest out.json]

<trainer folder> = .../Dataset004_WML/nnUNetTrainer_8000epochs__nnUNetPlans__3d_fullres
(it must contain plans.json, dataset.json and fold_<fold>/checkpoint_final.pth).

Adapted from Neurodesk webapps apps/white-matter-lesions/scripts/export_model.py
(https://github.com/neurodesk/webapps, Apache-2.0). Changes by MSTool-AI: the network is built
with nnunetv2's own get_network_from_plans (not a hand-written PlainConvUNet call); every graph
stage is compared with the PyTorch checkpoint itself (not only with the first ONNX export);
a JSON manifest (sha256, bytes, versions, max logit deviation) is written for the app's pin.

Graph changes (all arithmetic-preserving, each verified below):
1. ConvTranspose (kernel == stride, no padding) -> 1x1x1 Conv + depth-to-space Reshape/Transpose,
   because ONNX Runtime Web's WebGPU backend has no 3D ConvTranspose.
2. Initialisers >= 1024 elements stored as float16 with a Cast to float32 in the graph
   (download halves; arithmetic stays float32).
"""
import argparse, hashlib, json, sys, tempfile, platform
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from onnx import helper, numpy_helper, shape_inference, TensorProto

CHECKPOINT_SHA256 = [
    '4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861',
    '3966dd256074a0ea3c7d16c3a8e7412a6cb5071220df71b54745aeb50c33c33c',
    '734be69b968cc6578bcf079bb79db166cd8f5edba0f0dc19a62bbe68021364d8',
    '8e989caccdcf45368cc8f1ef8a00598f9f072c1fbe23e57458fc572fea434c3f',
    'ff723a2eda28a7f78f75d96a993d029ea8f65aa3657f5aea7caab9b217792df2',
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def build_network(root: Path, fold: int):
    from nnunetv2.utilities.get_network_from_plans import get_network_from_plans
    plans = json.loads((root / 'plans.json').read_text())
    cfg = plans['configurations']['3d_fullres']
    arch = cfg['architecture']
    net = get_network_from_plans(arch['network_class_name'], arch['arch_kwargs'], arch['_kw_requires_import'],
                                 input_channels=1, output_channels=2, allow_init=True, deep_supervision=False)
    ckpt = root / f'fold_{fold}' / 'checkpoint_final.pth'
    digest = sha256(ckpt)
    if digest != CHECKPOINT_SHA256[fold]:
        sys.exit(f'unexpected checkpoint sha256 {digest} for fold {fold}')
    state = torch.load(ckpt, map_location='cpu', weights_only=False)['network_weights']
    state = {k.replace('_orig_mod.', ''): v for k, v in state.items()}
    net.load_state_dict(state)
    net.eval()
    return net, cfg['patch_size'], digest


def attribute(node, name):
    return next(helper.get_attribute_value(a) for a in node.attribute if a.name == name)


def replace_transposed_convolutions(model):
    model = shape_inference.infer_shapes(model)
    graph = model.graph
    initializers = {i.name: i for i in graph.initializer}
    shapes = {v.name: [d.dim_value for d in v.type.tensor_type.shape.dim] for v in graph.value_info}
    nodes, replaced = [], 0
    for node in graph.node:
        if node.op_type != 'ConvTranspose':
            nodes.append(node)
            continue
        kernel = attribute(node, 'kernel_shape')
        pads = [a for a in node.attribute if a.name == 'pads']
        assert kernel == attribute(node, 'strides') and (not pads or not any(attribute(node, 'pads'))), node.name
        assert not [a for a in node.attribute if a.name == 'group'] or attribute(node, 'group') == 1, node.name
        weight = numpy_helper.to_array(initializers[node.input[1]])
        bias = numpy_helper.to_array(initializers[node.input[2]])
        inputs, outputs = weight.shape[:2]
        taps = int(np.prod(kernel))
        n, _, d, h, w = shapes[node.input[0]]
        name = node.name.strip('/').replace('/', '_')
        graph.initializer.extend([
            numpy_helper.from_array(weight.reshape(inputs, outputs * taps).T.reshape(outputs * taps, inputs, 1, 1, 1), name + '_weight'),
            numpy_helper.from_array(np.repeat(bias, taps), name + '_bias'),
            numpy_helper.from_array(np.array([n, outputs, *kernel, d, h, w], np.int64), name + '_split'),
            numpy_helper.from_array(np.array([n, outputs, d * kernel[0], h * kernel[1], w * kernel[2]], np.int64), name + '_merge'),
        ])
        nodes += [
            helper.make_node('Conv', [node.input[0], name + '_weight', name + '_bias'], [name + '_taps'], kernel_shape=[1, 1, 1], name=name + '_conv'),
            helper.make_node('Reshape', [name + '_taps', name + '_split'], [name + '_split_out'], name=name + '_split'),
            helper.make_node('Transpose', [name + '_split_out'], [name + '_shuffled'], perm=[0, 1, 5, 2, 6, 3, 7, 4], name=name + '_shuffle'),
            helper.make_node('Reshape', [name + '_shuffled', name + '_merge'], [node.output[0]], name=name + '_merge'),
        ]
        graph.initializer.remove(initializers[node.input[1]])
        graph.initializer.remove(initializers[node.input[2]])
        replaced += 1
    del graph.node[:]
    graph.node.extend(nodes)
    del graph.value_info[:]
    return model, replaced


def store_half_precision(model):
    graph = model.graph
    casts = []
    for initializer in list(graph.initializer):
        value = numpy_helper.to_array(initializer)
        if value.dtype != np.float32 or value.size < 1024:
            continue
        half = numpy_helper.from_array(value.astype(np.float16), initializer.name + '_f16')
        graph.initializer.remove(initializer)
        graph.initializer.append(half)
        casts.append(helper.make_node('Cast', [half.name], [initializer.name], to=TensorProto.FLOAT, name=initializer.name + '_cast'))
    for cast in reversed(casts):
        graph.node.insert(0, cast)
    return model


def ort_logits(path, x):
    so = ort.SessionOptions()
    so.intra_op_num_threads = 8
    return ort.InferenceSession(str(path), so, providers=['CPUExecutionProvider']).run(None, {'input': x})[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    ap.add_argument('fold', type=int)
    ap.add_argument('out', type=Path)
    ap.add_argument('--manifest', type=Path)
    a = ap.parse_args()
    torch.set_num_threads(8)
    net, patch, ckpt_sha = build_network(a.root, a.fold)
    x = np.random.default_rng(0).standard_normal((1, 1, *patch)).astype(np.float32)
    with torch.no_grad():
        reference = net(torch.from_numpy(x)).numpy()
    report = {}
    with tempfile.TemporaryDirectory() as scratch:
        exported = Path(scratch) / 'fold.onnx'
        torch.onnx.export(net, torch.zeros(1, 1, *patch), str(exported), input_names=['input'], output_names=['logits'],
                          opset_version=17, dynamo=False)
        report['torch_vs_onnx_max_abs'] = float(np.abs(ort_logits(exported, x) - reference).max())
        rewritten = Path(scratch) / 'fold-conv.onnx'
        model, replaced = replace_transposed_convolutions(onnx.load(exported))
        onnx.save(model, rewritten)
        report['convtranspose_replaced'] = replaced
        report['torch_vs_rewritten_max_abs'] = float(np.abs(ort_logits(rewritten, x) - reference).max())
        model = store_half_precision(onnx.load(rewritten))
        onnx.checker.check_model(model)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        onnx.save(model, a.out)
    final = ort_logits(a.out, x)
    report['torch_vs_final_max_abs'] = float(np.abs(final - reference).max())
    report['class_agreement_random_patch'] = float(((final[0, 1] > final[0, 0]) == (reference[0, 1] > reference[0, 0])).mean())
    manifest = {
        'filename': a.out.name,
        'fold': a.fold,
        'bytes': a.out.stat().st_size,
        'sha256': sha256(a.out),
        'source_checkpoint_sha256': ckpt_sha,
        'source': 'Zenodo 10.5281/zenodo.17955359 v2.0 Dataset004_WML.zip (md5 8b90b789d6ceca1886f42fa1724a08cc), '
                  'nnUNetTrainer_8000epochs__nnUNetPlans__3d_fullres/fold_%d/checkpoint_final.pth' % a.fold,
        'license': 'CC-BY-4.0 (FLAMeS weights, Dereskewicz/La Rosa et al.); converted to ONNX (format change, float16 storage)',
        'patch_size': patch,
        'input': 'input [1,1,%d,%d,%d] float32' % tuple(patch),
        'output': 'logits [1,2,%d,%d,%d] float32 (0=background, 1=lesion)' % tuple(patch),
        'opset': 17,
        'checks': report,
        'versions': {'torch': torch.__version__, 'onnx': onnx.__version__, 'onnxruntime': ort.__version__,
                     'python': platform.python_version()},
    }
    print(json.dumps(manifest, indent=1))
    if a.manifest:
        a.manifest.write_text(json.dumps(manifest, indent=1))


if __name__ == '__main__':
    main()
