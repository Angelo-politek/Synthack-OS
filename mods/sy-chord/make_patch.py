from __future__ import annotations
import argparse, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
LOAD = 0x40000400
STOCK_HASH = "8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e"
sys.path.insert(0, str(ROOT / "tools" / "unpack"))
import eft
def digest(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def patch_regions(old, new, section, regions):
    result = []
    for r in (r for r in regions if r["section"] == section):
        a, b = r["start"], r["end"]
        if old[a:b] != new[a:b]:
            result.append({"section":section,"addr":f"0x{LOAD+a:08x}","len":b-a,"expect_sha256":digest(old[a:b]),"hex":new[a:b].hex()})
    return result
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stock", type=Path, required=True); p.add_argument("--node", required=True)
    p.add_argument("--output", type=Path, default=Path(__file__).with_name("patch.json")); args = p.parse_args()
    if digest(args.stock.read_bytes()) != STOCK_HASH: raise SystemExit("stock OS 1.41 SHA-256 mismatch")
    with tempfile.TemporaryDirectory(prefix="sy-chord-") as t:
        t = Path(t); src = eft.unpack(args.stock, t / "stock", ids=[3,7]); o3,o7,meta=t/"new3",t/"new7",t/"meta.json"
        subprocess.run([args.node,str(Path(__file__).with_name("generate.mjs")),str(src[3]),str(src[7]),str(o3),str(o7),str(meta)],check=True)
        old={n:src[n].read_bytes() for n in (3,7)}; new={3:o3.read_bytes(),7:o7.read_bytes()}; regions=json.loads(meta.read_text())["regions"]
        patches=patch_regions(old[3],new[3],3,regions)+patch_regions(old[7],new[7],7,regions)
        if not patches: raise SystemExit("generator made no changes")
        args.output.write_text(json.dumps({"name":"sy-chord","os":"1.41","description":"31-wave SY CHORD bank and matching waveform graphics; WAVE 0 remains stock.","generated_by":"mods/sy-chord/make_patch.py","patches":patches},indent=2)+"\n")
if __name__ == "__main__": main()
