"""Local, offline browser smoke harness for the BUILT in-browser FLAMeS worker (no app, no backend, no auth).

    python -I serve.py --dist <frontend/dist> --model <flames-fold0.onnx> --flair <public FLAIR.nii.gz> --out <dir> [--port 8765]

Serves on 127.0.0.1 only, with Cross-Origin-Opener-Policy / Cross-Origin-Embedder-Policy so the page is
cross-origin isolated (WebAssembly threads). Routes:
  GET  /harness.html                         the harness page (this folder)
  GET  /assets/*                             the Vite build output (worker + ONNX Runtime Web wasm)
  GET  /models/flames/flames-fold0-2a10bb9d.onnx   the exported model
  GET  /flair.nii.gz                         the public FLAIR
  POST /log, /result, /mask                  the page reports back; written to --out
Then open http://127.0.0.1:<port>/harness.html?worker=/assets/<flamesInBrowser.worker-*.js>&webgpu=0|1
"""
import argparse, json, os, sys, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

TYPES = {'.js': 'text/javascript', '.mjs': 'text/javascript', '.wasm': 'application/wasm', '.html': 'text/html',
         '.onnx': 'application/octet-stream', '.gz': 'application/octet-stream', '.json': 'application/json'}


def make_handler(args):
    here = Path(__file__).resolve().parent
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def _headers(self, code, ctype, length):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(length))
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

        def do_GET(self):
            path = self.path.split('?')[0]
            if path == '/harness.html':
                f = here / 'harness.html'
            elif path == '/flair.nii.gz':
                f = Path(args.flair)
            elif path == '/models/flames/flames-fold0-2a10bb9d.onnx':
                f = Path(args.model)
                with open(out / 'requests.log', 'a') as log:
                    log.write(f'{time.strftime("%H:%M:%S")} model download\n')
            elif path.startswith('/assets/') and '..' not in path:
                f = Path(args.dist) / path.lstrip('/')
            else:
                self._headers(404, 'text/plain', 0)
                return
            if not f.is_file():
                self._headers(404, 'text/plain', 0)
                return
            data = f.read_bytes()
            self._headers(200, TYPES.get(f.suffix, 'application/octet-stream'), len(data))
            self.wfile.write(data)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            name = self.path.strip('/').split('?')[0]
            if name == 'log':
                with open(out / 'browser.log', 'a', encoding='utf-8') as log:
                    log.write(f'{time.strftime("%H:%M:%S")} {body.decode("utf-8", "replace")}\n')
            elif name == 'result':
                (out / f'result-{int(time.time())}.json').write_bytes(body)
            elif name == 'mask':
                (out / f'mask-{int(time.time())}.u8').write_bytes(body)
            self._headers(204, 'text/plain', 0)

        def log_message(self, *a):
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dist', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--flair', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', a.port), make_handler(a))
    print(f'pid {os.getpid()} serving http://127.0.0.1:{a.port}/harness.html', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
