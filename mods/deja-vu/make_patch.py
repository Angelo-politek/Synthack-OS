"""Build the OS 1.41 Déjà Vu LFO patch manifest. No firmware bytes are committed."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; REPO=HERE.parents[1]; sys.path.insert(0,str(REPO/'tools'/'unpack'))
import eft
from lfo_dv import SECTION,BASE,REGIONS,build_section

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 stock=REPO/'firmware'/'Syntakt_OS1.41.syx'
 if not stock.exists(): raise SystemExit('missing official stock input: '+str(stock))
 sec=eft.unpack(stock,REPO/'unpacked'/stock.stem,ids=[SECTION])[SECTION].read_bytes(); out=build_section(sec); patches=[]
 for start,end,label in REGIONS:
  old=sec[start-BASE:end-BASE]; new=out[start-BASE:end-BASE]
  if old!=new: patches.append({'section':SECTION,'addr':f'{start:#010X}','len':end-start,'expect_sha256':sha(old),'hex':new.hex(),'what':label})
 spec={'name':'deja-vu','os':'1.41','description':'DV-F and DV-T looping random LFO shapes after RND. SPH controls regeneration; MODE controls 2, 4, 8, 16, or 32 steps.','generated_by':'mods/deja-vu/make_patch.py','patches':patches}
 (HERE/'patch.json').write_text(json.dumps(spec,indent=2)+'\n');print(f'patch.json: {len(patches)} section-3 regions')
if __name__=='__main__':main()
