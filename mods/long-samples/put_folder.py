"""Send every WAV of a folder as long samples, with Synfact's tool (SPDX-License-Identifier: GPL-2.0-or-later).

    cd synfact-dev
    python ../mods/long-samples/put_folder.py "C:/Users/me/Music/Syntakt/Sample" --skip "MagMag"

- Names: the file name without extension, cut to 32 UTF-8 bytes (HZFS limit), unique.
- --skip TEXT (repeatable): leave out the files whose name contains TEXT.
- --dry-run: show the names, send nothing.
- One file at a time; a failed file is reported and the next one goes on.
The SAMPLER plays the first 64 files of the catalogue (L1..L64), as long as the voice CPU has room (~31 MB).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def short(name: str, used: set[str]) -> str:
    base = name.strip()
    while len(base.encode("utf-8")) > 32:
        base = base[:-1].rstrip()
    out, n = base, 2
    while out in used:
        tail = f"~{n}"
        stem = base
        while len((stem + tail).encode("utf-8")) > 32:
            stem = stem[:-1]
        out, n = stem.rstrip() + tail, n + 1
    used.add(out)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder")
    p.add_argument("--skip", action="append", default=[])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--port", default="Syntakt")
    a = p.parse_args()
    files = sorted(f for f in Path(a.folder).iterdir() if f.suffix.lower() == ".wav"
                   and not any(s.lower() in f.name.lower() for s in a.skip))
    if not files:
        print("no WAV files")
        return 1
    used: set[str] = set()
    ok = 0
    for f in files:
        name = short(f.stem, used)
        print(f"{name!r:36} <- {f.name}")
        if a.dry_run:
            continue
        r = subprocess.run([sys.executable, "-m", "elekloader.sdk.syntakt.long_samples", "--port", a.port,
                            "put", str(f), "--name", name, "--yes-write-device"])
        if r.returncode:
            print(f"  [!] failed: {f.name}")
        else:
            ok += 1
    if not a.dry_run:
        print(f"{ok} of {len(files)} sent. Power cycle the Syntakt to load them.")
    return 0 if a.dry_run or ok == len(files) else 2


if __name__ == "__main__":
    sys.exit(main())
