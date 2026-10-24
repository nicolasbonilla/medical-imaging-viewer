"""Object store used by the training job: Google Cloud Storage, or a local folder for tests.

FT_STORE = "gs://mstool-research-data"  (default)  or  "local:C:/some/folder"  (tests, no cloud).
Object names are bucket-relative ("flames-thick/train/<run>/...").
"""
import os
import shutil

BUCKET_ONLY = "mstool-research-data"


class LocalStore:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _p(self, name):
        return os.path.join(self.root, *name.split("/"))

    def exists(self, name):
        return os.path.isfile(self._p(name))

    def download(self, name, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        shutil.copyfile(self._p(name), path)

    def upload(self, path, name):
        os.makedirs(os.path.dirname(self._p(name)), exist_ok=True)
        tmp = self._p(name) + ".part"
        shutil.copyfile(path, tmp)
        os.replace(tmp, self._p(name))                 # atomic like a GCS object write

    def read_text(self, name):
        with open(self._p(name), encoding="utf-8") as f:
            return f.read()

    def write_text(self, name, text):
        os.makedirs(os.path.dirname(self._p(name)), exist_ok=True)
        tmp = self._p(name) + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, self._p(name))

    def list(self, prefix):
        base = self._p(prefix)
        out = []
        for d, _, files in os.walk(base):
            for f in files:
                if not f.endswith(".part"):
                    rel = os.path.relpath(os.path.join(d, f), self.root).replace(os.sep, "/")
                    out.append(rel)
        return sorted(out)

    def url(self, name):
        return self._p(name)


class GCSStore:
    def __init__(self, bucket):
        if bucket != BUCKET_ONLY:
            raise SystemExit(f"refusing bucket {bucket!r}: research jobs write only to {BUCKET_ONLY}")
        from google.cloud import storage
        self.bucket = storage.Client().bucket(bucket)
        self.name = bucket

    def exists(self, name):
        return self.bucket.blob(name).exists()

    def download(self, name, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.bucket.blob(name).download_to_filename(path)

    def upload(self, path, name):
        b = self.bucket.blob(name)
        b.chunk_size = 64 * 1024 * 1024                 # resumable upload for checkpoints
        b.upload_from_filename(path)

    def read_text(self, name):
        return self.bucket.blob(name).download_as_text()

    def write_text(self, name, text):
        self.bucket.blob(name).upload_from_string(text, content_type="application/json")

    def list(self, prefix):
        return sorted(b.name for b in self.bucket.list_blobs(prefix=prefix))

    def url(self, name):
        return f"gs://{self.name}/{name}"


def open_store(spec=None):
    spec = spec or os.environ.get("FT_STORE", f"gs://{BUCKET_ONLY}")
    if spec.startswith("local:"):
        return LocalStore(spec[len("local:"):])
    if spec.startswith("gs://"):
        return GCSStore(spec[len("gs://"):].strip("/"))
    raise ValueError(f"unknown store {spec!r}")
