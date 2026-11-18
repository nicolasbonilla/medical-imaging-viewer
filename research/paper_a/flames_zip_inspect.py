#!/usr/bin/env python3
"""Paper A v0.2 — training-set provenance probe for the published FLAMeS weights.

Question: WHICH 20 of the 30 Ljubljana (open_ms_data / PubMRI, Lesjak 2018) scans did FLAMeS train
on? The paper (Dereskewicz et al., J Neuroimaging 2025, PMC12426979, Table 1) lists "PubMRI: 20"
but not which 20. nnU-Net result folders sometimes ship split / fingerprint / validation files
that name the training cases, so we inspect the released archive.

The archive is 2.35 GB, so it is NOT downloaded: zipfile reads the central directory and the few
small JSON/text members through HTTP Range requests (a seekable remote file). Only members
smaller than MAX_MEMBER bytes are fetched, into OUT_DIR (treated as untrusted data; only parsed as
JSON/text, never executed).

    python -I research/paper_a/flames_zip_inspect.py <out_dir>
"""
import io
import json
import os
import sys
import urllib.request
import zipfile

URLS = [
    "https://zenodo.org/api/records/17955359/files/Dataset004_WML.zip/content",
    "https://huggingface.co/FrancescoLR/FLAMeS-model/resolve/main/Dataset004_WML.zip",
]
MAX_MEMBER = 5_000_000
TEXT_EXT = (".json", ".txt", ".csv", ".pkl_not", ".md", ".log", ".yaml", ".yml")


class HttpRangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            cr = r.headers.get("Content-Range")
            self.size = int(cr.split("/")[-1])
            self.final_url = r.geturl()
        self.fetched = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.size, self.pos + n) - 1
        req = urllib.request.Request(self.final_url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
        self.pos += len(data)
        self.fetched += len(data)
        return data

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def main():
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    last_err = None
    for url in URLS:
        try:
            f = HttpRangeFile(url)
            break
        except Exception as e:                      # pragma: no cover - network
            last_err = e
    else:
        sys.exit(f"could not open archive: {last_err}")
    print(f"archive: {url}\n  size {f.size} bytes")
    zf = zipfile.ZipFile(io.BufferedReader(f, buffer_size=1 << 16))
    infos = zf.infolist()
    listing = [(i.filename, i.file_size) for i in infos]
    with open(os.path.join(out_dir, "_listing.json"), "w", encoding="utf-8") as fh:
        json.dump(listing, fh, indent=1)
    print(f"  {len(infos)} members:")
    for name, size in listing:
        print(f"    {size:>12d}  {name}")
    for i in infos:
        if i.is_dir() or i.file_size > MAX_MEMBER:
            continue
        if not i.filename.lower().endswith(TEXT_EXT):
            continue
        data = zf.read(i)
        dst = os.path.join(out_dir, i.filename.replace("/", "__"))
        with open(dst, "wb") as fh:
            fh.write(data)
        print(f"  fetched {i.filename} ({len(data)} bytes)")
    print(f"total bytes transferred: {f.fetched}")


if __name__ == "__main__":
    main()
