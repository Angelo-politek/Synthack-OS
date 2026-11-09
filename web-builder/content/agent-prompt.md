You are helping me write a SyntHack OS mod for the Elektron Syntakt, in this clone of
https://github.com/Angelo-politek/Synthack-OS. Target: Syntakt OS 1.42. Follow these steps.

1. Read first:
   CONTRIBUTING.md, LEGAL.md, RECOVERY.md, docs/writing-style.md, web-builder/content/modders.md,
   docs/modding-guide.md, docs/registry.md, docs/memory-map.md, docs/audio-path.md,
   docs/ui-parameters.md, docs/firmware-format.md, docs/emulation.md,
   tools/build/build.py, tools/build/registry.py, tests/test_registry.py, tests/test_cpu_budget.py,
   and the README, make_patch.py and test of the existing mod closest to my idea.
   docs/ uses 1.41 addresses: convert them with tools/build/osmap.py.

2. Ask me what the mod does on the device: keys, pages, parameters, what is saved and where
   (kit, pattern, project), whether it touches audio. Don't code until it is clear.
   Propose a mod name (lowercase, dashes). Wait for my answer.

3. Scope: my branch from `dev`. Edit only mods/<name>/, tests/test_<name>.py, claims in
   tools/build/registry.py (kitstore_layout.py / projstore_layout.py if the mod stores data)
   and the regenerated docs/registry.md. Anything else: stop and tell me why.

4. Hard rules:
   - No Elektron firmware bytes in the repository: no .syx, no extracted sections, no disassembly
     dumps, no copied OS code or data. patch.json holds addresses, the SHA-256 of the expected
     original bytes, and our bytes.
   - Never touch sections 2 (bootstrap) or 6 (boot). Don't make the boot longer.
   - Claim every shared resource in tools/build/registry.py before using it: mod-area range,
     boot-list slot, engine area, shared RAM, section 3 bytes, vparams slots, parameter ids,
     pages, kit or project storage.
     Then run python tools/build/registry.py.
   - Zero bytes are not free space. Put code in the mod area: "requires": ["modarea"],
     "append": true, linked at modarea_layout.RAM + the claimed offset.
   - Never use RAM above the BSS (0x45566490-0x48000000 on 1.42).
   - No .bss, no libgcc. ColdFire: no exg; movem only with (An) or d16(An); muls.l without
     absolute addresses; short branches within +-127 bytes.
   - OS functions return pointers in d0; m68k-linux-gnu-gcc reads pointer results from a0.
     Declare OS functions with an integer return, then cast (tests/test_os_abi.py checks it).
     A std::string returned by value is built at the address passed in a0: write that call in
     assembly, as the wrapper in mods/syn-pages/synpages.c.
   - Setup at boot: a short function in the mod area's boot list (claimed slot in BOOT_SLOTS),
     never anything that makes the boot longer.
   - Hooks replay the instructions they replace and save every register they use.
   - Stored data survives the OS save -> reload. Files saved with the mod load safely on the stock
     OS and on builds without it (zero = default).
   - Parameter ids pass tests/test_id_audit.py: no aliases, no MIDI CC/NRPN, no ids of other mods.

5. Generate patch.json only with mods/<name>/make_patch.py (m68k-linux-gnu-as or -gcc,
   -mcpu=54418). Never edit patch.json by hand. "name" = folder name. "os": "1.42".

6. Write tests/test_<name>.py: load the stock section in the emulator (tools/emu, Unicorn),
   apply the patch, run the ORIGINAL OS code around it, compare with stock. Cover every hook,
   every stored value (save -> reload through the OS writer and reader; old files without the
   data) and edge cases. Skip tests that need the stock OS when firmware/ is empty.

7. Audio code: count the instructions it adds per 32-sample block in the emulator, idle and worst
   case, as counted() in tests/test_cpu_budget.py. Add a cost regression test. The stock OS uses
   ~89 % of that interrupt: do nothing when idle. Report the numbers to me.

8. Add mods/<name>/mod.json: exactly {"title", "kind", "status", "summary"}, status "experimental"; kind "feature" ("machine" for
   a synth machine); summary one sentence, ASCII English. Add mods/<name>/README.md: use on the
   device, how it works (hooks, addresses), tests, credits. Follow docs/writing-style.md.

9. Build with all other mods:
   python tools/build/build.py --stock firmware/<stock>.syx mods/<name> mods/splash mods/dual-mono \
     mods/master-comp mods/readable-values mods/perf-fx mods/fx3 mods/sy-fm4 mods/sampler -o out/test.syx

10. Run until everything passes:
    python -m pytest
    cd web-builder && npm test && npm run build
    python tools/build/registry.py && git diff --exit-code docs/registry.md

11. Don't commit, push or open the pull request. Write a pull request description for `dev`:
    what the mod does, files, resources claimed, tests (which ran with the stock OS), audio cost
    per block, what still needs testing on the device, credits and licenses. Then tell me to
    flash and test on the device before I submit.

Never post the mod or instructions on Elektronauts: it is forbidden there.
If a rule conflicts with my request, tell me. Don't work around it.
