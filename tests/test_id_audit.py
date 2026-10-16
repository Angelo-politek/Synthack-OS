"""Id dei parametri usati dalle mod: nessun alias di un parametro dell'OS, nessun CC/NRPN MIDI.

"Nascosto" non vuol dire libero: un id con lo stesso gruppo + id interno di un parametro visibile e' un
alias che l'OS puo' mettere su una pagina (59 GAIN al posto di RESO, 122 sul MIXER, 113 mix del delay...).
Con vparams al suo posto quella manopola mostrerebbe la mod (issue #3). Un id con CC o NRPN riceverebbe
i messaggi MIDI dell'utente. Il test legge i descrittori dall'OS stock e gli id da tutti i patch.json.
"""

import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "unpack")]
import eft  # noqa: E402

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS Syntakt assente")

LOAD, DESC, N = 0x4000_0400, 0x4022_D59C, 505
NONE = 0xFFFF_FFFF
# id nativi riusati per quello che sono (salvati per traccia dall'OS): fx3 SND3 = "Delay Time" dell'amp
NATIVE = {"fx3": {72}}
# alias che l'OS mostra davvero (visti sulla macchina o nel codice delle pagine): mai da usare
KNOWN_VISIBLE = {59, 91, 101, 113, 122, 125, 127}


@pytest.fixture(scope="module")
def desc():
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    out = []
    for i in range(N):
        o = DESC - LOAD + 52 * i
        group, iid = struct.unpack(">ii", sec3[o:o + 8])
        cc, nrpn = struct.unpack(">II", sec3[o + 24:o + 32])
        out.append((group, iid, cc, nrpn))
    return out


def virtual_ids():
    """{mod: {id}} dagli elementi della tabella di vparams registrati da ogni mod."""
    ids = defaultdict(set)
    for f in sorted((ROOT / "mods").glob("*/patch.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        for p in spec["patches"]:
            if p.get("append") and p.get("what", "").startswith("vparams["):
                ids[spec["name"]].add(struct.unpack(">H", bytes.fromhex(p["hex"])[:2])[0])
    return ids


def test_some_mods_register_virtual_ids():
    assert {"master-comp", "fx3"} <= set(virtual_ids())


@pytest.mark.parametrize("mod", ["master-comp", "fx3"])
def test_ids_are_not_aliases_and_have_no_midi(desc, mod):
    keys = defaultdict(list)
    for i, (g, iid, _, _) in enumerate(desc):
        keys[(g, iid)].append(i)
    for i in virtual_ids()[mod] | NATIVE.get(mod, set()):
        g, iid, cc, nrpn = desc[i]
        assert i not in KNOWN_VISIBLE, (mod, i)
        assert keys[(g, iid)] == [i], f"{mod}: id {i} e' alias di {[j for j in keys[(g, iid)] if j != i]}"
        assert cc == NONE and nrpn == NONE, f"{mod}: id {i} ha CC/NRPN ({cc:#x}, {nrpn:#x})"


def test_mods_do_not_share_ids():
    seen = {}
    for mod, ids in virtual_ids().items():
        for i in ids | NATIVE.get(mod, set()):
            assert i not in seen, f"id {i}: {seen[i]} e {mod}"
            seen[i] = mod


MOD_DEST = 0xE00                                # descrittore +36: destinazione di modulazione (LFO)
INTENDED_DEST = {72}                            # SND3 di fx3: modulabile come le mandate DEL/REV
# L'elenco delle destinazioni (0x4001471C) prende gli id del modello della traccia: i gruppi delle tracce
# MIDI della Digitakt (56..58) non ci sono sulla Syntakt, quindi i loro id non compaiono mai.
UNREACHABLE_GROUPS = {56, 57, 58}


def renamed_ids():
    """{id: mod} dei descrittori a cui una mod cambia il nome (+40 o +48)."""
    out = {}
    for f in sorted((ROOT / "mods").glob("*/patch.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        for p in spec["patches"]:
            if p.get("append"):
                continue
            off = int(p["addr"], 16) - DESC
            if 0 <= off < 52 * N and off % 52 in (40, 48):
                out[off // 52] = spec["name"]
    return out


def built_desc():
    """Descrittori dopo le patch di tutte le mod: {id: flag +36}."""
    sec3 = bytearray(eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes())
    for f in sorted((ROOT / "mods").glob("*/patch.json")):
        for p in json.loads(f.read_text(encoding="utf-8"))["patches"]:
            if not p.get("append") and p["section"] == 3:
                a = int(p["addr"], 16) - LOAD
                data = bytes.fromhex(p["hex"]) if "hex" in p else p["ascii"].encode("latin1")
                sec3[a:a + len(data)] = data
    return {i: struct.unpack(">iI", sec3[DESC - LOAD + 52 * i:DESC - LOAD + 52 * i + 4]
                             + sec3[DESC - LOAD + 52 * i + 36:DESC - LOAD + 52 * i + 40]) for i in range(N)}


def test_renamed_parameters_are_modulation_targets_only_on_purpose():
    """Un parametro rinominato da una mod che resta destinazione degli LFO apparirebbe con il nuovo nome ma
    modulerebbe il parametro originale dell'OS (era il caso di RPT2 = Reverb FX Routing fino alla v0.8)."""
    desc = built_desc()
    for i, mod in renamed_ids().items():
        group, cap = desc[i]
        if i in INTENDED_DEST:
            assert cap & MOD_DEST == MOD_DEST, (mod, i)
        elif group not in UNREACHABLE_GROUPS:
            assert cap & MOD_DEST == 0, f"{mod}: id {i} rinominato ma ancora destinazione LFO"
