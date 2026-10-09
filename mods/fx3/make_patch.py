"""Mod fx3: costruisce patch.json da fx3.c (terza mandata effetti, chorus).

- compila fx3.c per ColdFire e lo collega nell'area mod a 0x4600A000 (tabelle generate qui);
- aggancia la funzione di mix a blocchi: ciclo per traccia (0x4008F3A0), delay (0x4008F828: bus 3,
  chorus e mandata verso il delay), somme del master (0x4008FB04);
- SND3 = id 72 (nascosto, salvato per traccia) nella casella E della pagina AMP 2;
- pagina FX3 = pagina 25 dell'OS ("OB8", inutilizzata) come seconda pagina del tab REVERB, con gli id
  nascosti delle tracce MIDI 246..253 tramite vparams.

    python mods/fx3/make_patch.py            # build normale
    python mods/fx3/make_patch.py --meter    # prova: carico dell'interrupt audio nella casella TYPE
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "unpack"))
import eft  # noqa: E402

_vp = importlib.util.spec_from_file_location("vparams_make_patch", REPO / "mods" / "vparams" / "make_patch.py")
vparams = importlib.util.module_from_spec(_vp)
_vp.loader.exec_module(vparams)

LOAD = 0x4000_0400
MODAREA_RAM, MODAREA_IMG = 0x4600_0000, 0x4034_8000
CODE_BASE, CODE_END = MODAREA_RAM + 0xA000, MODAREA_RAM + 0xDFF0   # retroazione e mandata a +0xDFF8.., linea a +0xE000 (8 KB)
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"
FS = 48000
DESC = 0x4022_D59C
P_PLAIN, G_KNOB, G_SEND, S_BAR = 0x41B9_DFD0, 0x41B9_DCD0, 0x41B9_DBD0, 0x41B9_D5D0
VP_SLOT = 9                             # posti 9..15 della tabella di vparams

HOOKS = [  # (indirizzo, byte originali, simbolo, jsr/jmp, riempimento con nop)
    (0x4008_F3A0, "ae000900ae810900", "fx3_trk_hook", "ciclo per traccia: jsr fx3_trk_hook ; nop"),
    (0x4008_F828, "4eb940096890", "fx3_del_hook", "delay: jsr fx3_del_hook (bus 3, chorus, mandata al delay)"),
    (0x4008_FB04, "486efed848798000e0f0", "fx3_mix_hook", "somme del master: jsr fx3_mix_hook ; nop ; nop"),
    (0x4019_4E2A, "42b941b9f83c", "fx3_page_stub", "pagina 25 (FX3): caselle all'avvio"),
    (0x4019_4A50, "42b941b9f6a0", "fx3_amp_stub", "pagine AMP 2: casella E = SND3 (id 72)"),
]
# tab REVERB: vettore delle pagine {21} -> {21, 25}; nomi della pagina 25
REVERB_COUNT, REVERB_ARRAY = 0x4003_588C, 0x4003_5892
PAGE_NAMES = [(0x4019_4D96, "4024e947", "fx3_page_s", "pagina 25: nome breve"),
              (0x4019_4DDC, "40251b03", "fx3_page_l", "pagina 25: nome lungo")]
NO_STYLE = 0x41B9_FA68                 # +68 dell'id 0: std::function vuota (nessuno stile, come LFO MODE)
DRAW_HOOK, DRAW_ORIG = 0x4004_2CE0, "4fefffa048d77cfc"  # disegno dei tab DELAY/REVERB (caselle 5-6 = filtro)
# classe del tab AMP: gli id sotto 73 (diversi da 73-74) erano trattati come parti dell'inviluppo, senza
# grafica propria; con bra -> "casella normale" SND3 (72) disegna la sua icona
AMP_FIX = (0x4004_1E84, "605c", "6058")
# parametri della pagina: id, nomi, massimo, default; prototipi dell'oggetto {offset: (operando, atteso,
# nuovo)}; correzioni ai campi +0/+4 per comportarsi come DEL (250): tipo 0, prototipo d3
PARAMS = [
    (246, "TYPE", "FX3 Type", 0, 0,
     {20: (0x4018_F252, 0x41B9_DF60, "fx3_proto_type"), 36: (0x4018_F260, 0x41B9_DCC0, "fx3_proto_type_gfx"),
      68: (0x4018_F27C, 0x41B9_D670, NO_STYLE)},
     [(0x4018_F234, "2f05", "2f03"), (0x4018_F23C, "7005", "7000")]),
    (247, "SPD", "Chorus Speed", 127, 60,
     {20: (0x4018_F2A4, 0x41B9_DF60, "fx3_proto_spd"), 36: (0x4018_F2B2, 0x41B9_DCC0, G_KNOB)},
     [(0x4018_F290, "2f05", "2f03"), (0x4018_F292, "7204", "7200")]),
    (248, "DEP", "Chorus Depth", 127, 64,
     {20: (0x4018_F2F4, 0x41B9_DF60, "fx3_proto_dep"), 36: (0x4018_F302, 0x41B9_DCC0, G_KNOB)},
     [(0x4018_F2E2, "2f05", "2f03"), (0x4018_F2EA, "23c241ba4b84", "42b941ba4b84")]),
    (250, "TIME", "Chorus Delay", 127, 64, {20: (0x4018_F398, 0x41B9_DFD0, "fx3_proto_del")}, []),
    (251, "FDBK", "Chorus Feedback", 127, 0, {20: (0x4018_F3E8, 0x41B9_DFD0, "fx3_proto_fdbk")}, []),
    (252, "WID", "Chorus Width", 127, 64, {20: (0x4018_F438, 0x41B9_DFD0, "fx3_proto_wid")}, []),
    (249, "DEL", "FX3 to Delay", 127, 0,
     {20: (0x4018_F344, 0x41B9_DF40, "fx3_proto_vol"), 36: (0x4018_F356, 0x41B9_DC40, G_SEND),
      68: (0x4018_F372, 0x41B9_D670, S_BAR)},
     [(0x4018_F332, "2f04", "2f03")]),
    (253, "VOL", "FX3 Volume", 127, 100,
     {20: (0x4018_F48A, 0x41B9_DF60, "fx3_proto_vol"), 36: (0x4018_F49C, 0x41B9_DCC0, G_KNOB)},
     [(0x4018_F476, "2f05", "2f03"), (0x4018_F47E, "7004", "7000")]),
]
SND3 = {"id": 72, "g36": (0x4018_B37A, G_KNOB, G_SEND), "s68": (0x4018_B396, 0x41B9_D670, S_BAR)}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


# ---- tabelle (curve scelte qui, nessun dato dell'OS)
def spd_hz(v: int) -> float:
    return 0.05 * 200 ** (v / 127)                     # 0.05 .. 10 Hz


def del_ms(v: int) -> float:
    return 1 + 29 * (v / 127) ** 1.5                   # 1 .. 30 ms


def dep_ms(v: int) -> float:
    return 8 * (v / 127) ** 2                          # 0 .. 8 ms


def txt_hz(f: float) -> str:
    return f"{f:.2f}Hz" if f < 10 else f"{f:.1f}"


def txt_ms(m: float) -> str:
    return f"{m:.2f}ms" if m < 1 else f"{m:.1f}ms" if m < 10 else f"{m:.0f}ms"


def txt_db(g: float) -> str:
    return "-inf" if g <= 0 else f"{20 * math.log10(g):.1f}dB"


def tables() -> str:
    q8 = lambda ms: round(ms * FS / 1000 * 256)
    arr = lambda t, name, vals: f"static const {t} {name}[{len(vals)}] = {{{', '.join(str(v) for v in vals)}}};\n"
    txt = lambda name, vals: (f"static const char {name}[128][8] = {{" +
                              ", ".join(json.dumps(v) for v in vals) + "};\n")
    out = "/* generato da mods/fx3/make_patch.py */\n"
    out += arr("short", "SIN_T", [round(32767 * math.sin(2 * math.pi * i / 256)) for i in range(257)])
    out += arr("u32", "SPD_INC", [round(spd_hz(v) / FS * 2 ** 32) for v in range(128)])
    out += arr("u32", "DEL_Q8", [q8(del_ms(v)) for v in range(128)])
    out += arr("u32", "DEP_Q8", [q8(dep_ms(v)) for v in range(128)])
    out += arr("s32", "FB_Q15", [round(32767 * 0.9 * v / 127) for v in range(128)])
    out += arr("s32", "VOL_Q15", [round(32767 * (v / 127) ** 2) for v in range(128)])
    out += txt("SPD_TXT", [txt_hz(spd_hz(v)) for v in range(128)])
    out += txt("DEL_TXT", [txt_ms(del_ms(v)) for v in range(128)])
    out += txt("DEP_TXT", [txt_ms(dep_ms(v)) for v in range(128)])
    out += txt("VOL_TXT", [txt_db((v / 127) ** 2) for v in range(128)])
    return out


def names() -> str:
    return "".join(f'const char fx3_n{i}_s[] = "{s}";\nconst char fx3_n{i}_l[] = "{ln}";\n'
                   for i, (_, s, ln, *_r) in enumerate(PARAMS))


def build_blob(meter: bool) -> tuple[bytes, dict[str, int], str]:
    with tempfile.TemporaryDirectory(prefix="fx3-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "fx3.c", tmp / "fx3.c")
        (tmp / "fx3_tables.h").write_text(tables(), encoding="ascii")
        (tmp / "fx3_names.h").write_text(names(), encoding="ascii")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} {'-DMETER' if meter else ''} -c fx3.c -o fx3.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e fx3_block -o fx3.elf fx3.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u fx3.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        heads = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -h fx3.elf")
        for name, size in re.findall(r"^\s*\d+\s+(\.\S+)\s+([0-9a-f]+)", heads, re.M):
            if name in (".bss", ".sbss") and int(size, 16):
                raise SystemExit("fx3.c non deve avere variabili in .bss")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data fx3.elf fx3.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm fx3.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        dis = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -d -m m68k:isa-c:emac fx3.elf")
        blob = (tmp / "fx3.bin").read_bytes()
    return blob, syms, dis


# misuratore (solo prova): ingresso e uscita dell'interrupt audio
METER_HOOKS = [(0x400A_3856, "4e56ff5c48d73fff", "fx3_m_in", "interrupt audio, ingresso: jmp fx3_m_in ; nop"),
               (0x400A_54A0, "4cee3fffff5c4e5e", "fx3_m_out",
                "interrupt audio, uscita: jmp fx3_m_out ; nop")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meter", action="store_true", help="build di prova col misuratore di carico")
    a = ap.parse_args()
    stock = REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms, dis = build_blob(a.meter)
    if CODE_BASE + len(blob) > CODE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B")
    emac = [int(m[1], 16) for m in re.finditer(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4} ?)+\s+(\S+)\s*(.*)$", dis, re.M)
            if re.match(r"^(mac[lw]|msac[lw]|movclrl)$", m[2]) or re.search(r"%(acc|macsr|mask)", m[3])]
    sums = [x for x in emac if syms["fx3_sum8"] <= x < syms["fx3_sum_end"]]     # somme del bus
    allowed = sorted([syms["fx3_trk_hook"], syms["fx3_trk_hook"] + 4, syms["fx3_macsr"]] + sums)
    if emac != allowed or len(sums) != 14:
        raise SystemExit(f"EMAC fuori dai trampolini e dalle somme: {[hex(a) for a in emac]}")

    def fixed(addr: int, new: bytes, what: str, expect: str | None = None) -> dict:
        old = sec3[addr - LOAD:addr - LOAD + len(new)]
        if expect is not None and old.hex() != expect:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()} (attesi {expect})")
        return {"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                "hex": new.hex(), "what": what}

    long = lambda v: struct.pack(">I", v)
    patches = [{"section": 3, "addr": f"{MODAREA_IMG + CODE_BASE - MODAREA_RAM:#010X}", "len": len(blob),
                "append": True, "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) fx3.c"}]
    for addr, orig, sym, what in HOOKS:
        code = struct.pack(">HI", 0x4EB9, syms[sym])
        code += b"\x4e\x71" * ((len(orig) // 2 - len(code)) // 2)
        patches.append(fixed(addr, code, what, orig))
    if a.meter:
        for addr, orig, sym, what in METER_HOOKS:
            patches.append(fixed(addr, struct.pack(">HI", 0x4EF9, syms[sym]) + bytes.fromhex("4e71"), what, orig))
    patches.append(fixed(REVERB_COUNT, bytes.fromhex("7202"), "tab REVERB: 2 pagine", "7201"))
    patches.append(fixed(REVERB_ARRAY, long(syms["fx3_reverb_pages"]), "tab REVERB: pagine {21, 25}", "401c7fa8"))
    for addr, orig, sym, what in PAGE_NAMES:
        patches.append(fixed(addr, long(syms[sym]), what, orig))
    patches.append(fixed(DRAW_HOOK, struct.pack(">HI", 0x4EF9, syms["fx3_draw_hook"]) + bytes.fromhex("4e71"),
                         "tab DELAY/REVERB: pagina 25 col disegno generico a 8 caselle", DRAW_ORIG))
    patches.append(fixed(AMP_FIX[0], bytes.fromhex(AMP_FIX[2]), "tab AMP: SND3 (72) come casella normale",
                         AMP_FIX[1]))
    resolve = lambda v: syms[v] if isinstance(v, str) else v
    # SND3: id 72, icona propria e barra, nomi
    r = DESC + 52 * SND3["id"]
    for key, what in (("g36", "+36: grafica della mandata del delay"), ("s68", "+68: barra")):
        addr, orig, new = SND3[key]
        patches.append(fixed(addr, long(resolve(new)), f"id 72 (SND3) {what}", f"{orig:08x}"))
    patches += [fixed(r + 40, long(syms["fx3_snd_l"]), "id 72: nome lungo 'FX3 Send'"),
                fixed(r + 48, long(syms["fx3_snd_s"]), "id 72: nome breve 'FX3'")]
    # pagina FX3
    for n, (pid, short, ln, mx, df, protos, extra) in enumerate(PARAMS):
        r = DESC + 52 * pid
        patches.append(vparams.entry(VP_SLOT + n, pid, syms["fx3_get"], syms["fx3_set"], f"fx3 {short}"))
        patches += [fixed(r + 8, struct.pack(">III", 0, mx << 8, df << 8), f"id {pid} -> {short}: min, max, default"),
                    fixed(r + 40, long(syms[f"fx3_n{n}_l"]), f"id {pid}: nome lungo '{ln}'"),
                    fixed(r + 48, long(syms[f"fx3_n{n}_s"]), f"id {pid}: nome breve '{short}'")]
        for off, (addr, orig, new) in protos.items():
            patches.append(fixed(addr, long(resolve(new)), f"id {pid} +{off}: {resolve(new):#010x}", f"{orig:08x}"))
        for addr, orig, new in extra:
            patches.append(fixed(addr, bytes.fromhex(new), f"id {pid}: campo dell'oggetto come DEL (250)", orig))
    spec = {
        "name": "fx3", "os": "1.41", "requires": ["modarea", "vparams"],
        "description": "Terza mandata effetti: SND3 per traccia (pagina AMP 2) verso un chorus stereo; "
                       "regolazioni e livello di ritorno sulla pagina 2 del tab REVERB.",
        "generated_by": "mods/fx3/make_patch.py",
        "symbols": {k: f"{syms[k]:#010x}" for k in (
            "fx3_trk_hook", "fx3_del_hook", "fx3_macsr", "fx3_mix_hook", "fx3_page_stub", "fx3_amp_stub",
            "fx3_block", "fx3_out", "fx3_get", "fx3_set", "fx3_p", "fx3_tgt", "fx3_cur",
            "fx3_bus", "fx3_wet", "fx3_idle", "fx3_reverb_pages", "fx3_fmt_spd", "fx3_fmt_del", "fx3_fmt_dep",
            "fx3_fmt_type", "fx3_fmt_fdbk", "fx3_fmt_wid", "fx3_fmt_vol", "fx3_type_gfx",
            "fx3_draw_hook")},
        "emac_sites": [f"{x:#010x}" for x in allowed],
        "meter_symbols": {k: f"{syms[k]:#010x}" for k in ("fx3_m_in", "fx3_m_out", "fx3_meter", "fx3_m_t0",
                                                          "fx3_m_start", "fx3_m_avg", "fx3_m_max")} if a.meter else {},
        "meter": a.meter,
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPO / "out" / "fx3").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "fx3" / "fx3.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}..{CODE_BASE + len(blob):#x}")


if __name__ == "__main__":
    main()
