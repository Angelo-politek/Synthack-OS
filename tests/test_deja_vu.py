"""Pure checks for the MIT-attributed Déjà Vu section-3 generator.
Stock-image checks run only when the user supplies firmware locally.
"""
import hashlib
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'mods'/'deja-vu'))
import lfo_dv as dv


def test_generator_layout_and_distinct_modes():
    free=dv.generator(dv.CAVE+dv.L['SLOTS'],dv.CAVE+dv.L['PROB']+4,False)
    trig=dv.generator(dv.CAVE+dv.L['SLOTS'],dv.CAVE+dv.L['PROB']+4,True)
    assert free.endswith(bytes.fromhex('4cd7001c4fef000c4e75'))
    assert trig.endswith(bytes.fromhex('4cd7001c4fef000c4e75'))
    assert free != trig
    assert len(free)<dv.L['CODE_DVT']-dv.L['CODE_DVF']
    assert dv.L['CODE_DVT']+len(trig)<=dv.L['SLOTS']


def test_declared_regions_are_disjoint_and_cover_caves():
    assert all(a[1]<=b[0] for a,b in zip(dv.REGIONS,dv.REGIONS[1:]))
    assert (dv.CAVE,dv.CAVE+dv.CAVE_LEN,'DV code/names/pictures') in dv.REGIONS
    assert (dv.CAVE2,dv.CAVE2+dv.CAVE2_LEN,'MODE cell pictures') in dv.REGIONS


def test_loop_length_artwork_has_all_five_variants():
    assert dv.LENGTHS==('2','4','8','16','32')
    assert set(dv.DIGITS)=={'1','2','3','4','6','8'}
    assert len(dv.step_tile((3,11,6,13,1,9,4,12),(4,3,4,3,4,3,4,3),'closed'))==28


STOCK=ROOT/'firmware'/'Syntakt_OS1.41.syx'
@pytest.mark.skipif(not STOCK.exists(),reason='official stock firmware not present')
def test_stock_patch_ownership_and_shape_marker(tmp_path):
    sys.path.insert(0,str(ROOT/'tools'/'unpack'))
    import eft
    raw=eft.unpack(STOCK,tmp_path/'unpacked',ids=[3])[3].read_bytes()
    built=dv.build_section(raw)
    assert len(built)==len(raw)
    assert not dv.is_patched(raw)
    assert dv.is_patched(built)
    changed=[i for i,(a,b) in enumerate(zip(raw,built)) if a!=b]
    assert changed
    assert all(any(start-dv.BASE<=i<end-dv.BASE for start,end,_ in dv.REGIONS) for i in changed)
    for start,end,_ in dv.REGIONS:
        if end-start>=0x500:
            assert not any(raw[start-dv.BASE:end-dv.BASE])

def test_synthetic_section_changes_only_declared_ranges():
    raw=bytes(0x340000)
    built=dv.build_section(raw)
    assert dv.is_patched(built)
    changed=[i for i,(a,b) in enumerate(zip(raw,built)) if a!=b]
    assert changed
    assert all(any(start-dv.BASE<=i<end-dv.BASE for start,end,_ in dv.REGIONS) for i in changed)


def test_no_overlap_with_current_upstream_fixed_section_three_patches():
    import json
    for manifest in (ROOT/'mods').glob('*/patch.json'):
        if manifest.parent.name == 'deja-vu':
            continue
        spec=json.loads(manifest.read_text())
        for patch in spec.get('patches',[]):
            if patch.get('section')!=3 or patch.get('append'):
                continue
            addr=int(patch['addr'],0)
            end=addr+patch['len']
            assert not any(addr<hi and lo<end for lo,hi,_ in dv.REGIONS), (manifest,hex(addr),hex(end))
