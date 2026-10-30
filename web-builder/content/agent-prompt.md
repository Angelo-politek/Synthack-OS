You are helping me write a SyntHack OS mod for the Elektron Syntakt, in this clone of
https://github.com/Angelo-politek/Synthack-OS. Follow these instructions exactly.

1. Read first, before writing anything:
   CONTRIBUTING.md, LEGAL.md, RECOVERY.md, web-builder/content/modders.md,
   docs/modding-guide.md, docs/registry.md, docs/memory-map.md, docs/audio-path.md,
   docs/ui-parameters.md, docs/firmware-format.md, docs/emulation.md,
   tools/build/build.py, tools/build/registry.py, tests/test_registry.py, tests/test_cpu_budget.py,
   and the README, make_patch.py and test of the existing mod closest to my idea (mods/*/, tests/).
   Check which Syntakt OS version the mods target (the "os" field in mods/*/patch.json).

2. Ask me what the mod should do on the device: keys, pages, parameters, what is saved and where
   (kit, pattern, project), and whether it touches audio. Don't start coding until it is clear.
   Propose a mod name (lowercase, hyphens) and wait for my answer.

3. Work only in the branch I created from `dev`, inside mods/<name>/ and tests/test_<name>.py,
   plus resource claims in tools/build/registry.py (and kitstore_layout.py / projstore_layout.py
   if the mod stores data) and the regenerated docs/registry.md. Don't edit other mods or tools.
   If something outside that scope seems necessary, stop and tell me why.

4. Hard rules:
   - Never add Elektron firmware bytes to the repository: no .syx, no extracted sections, no
     disassembly dumps, no copied OS code or data. patch.json holds only addresses, the SHA-256 of
     the original bytes it expects, and our new bytes.
   - Never touch sections 2 (bootstrap) or 6 (boot). Don't make the boot longer.
   - Claim every shared resource (mod-area range, section 3 bytes, vparams slots, parameter ids,
     pages, kit or project storage) in tools/build/registry.py before using it, then run
     python tools/build/registry.py.
   - Zero bytes in the OS image are not free space. Use the mod area ("requires": ["modarea"],
     "append": true, linked at modarea_layout.RAM + the claimed offset).
   - Never use RAM above the BSS (0x45565490-0x48000000).
   - No .bss and no libgcc in mod code. Respect ColdFire limits: no exg, movem only with (An) or
     d16(An), muls.l without absolute addresses, short branches within +-127 bytes.
   - Hooks replay the instructions they replace and save every register they use.
   - Data saved in kits or projects must survive the OS's own save -> reload, and files saved with
     the mod must load safely on the stock OS and on builds without it (zero = default).
   - Parameter ids must pass tests/test_id_audit.py: no aliases, no MIDI CC/NRPN, no ids of other mods.

5. Generate patch.json only with mods/<name>/make_patch.py (m68k-linux-gnu-as or -gcc,
   -mcpu=54418). Never edit patch.json by hand. "name" must equal the folder name.

6. Write tests/test_<name>.py that loads the stock section in the emulator (tools/emu, Unicorn),
   applies the patch and runs the ORIGINAL OS code around it, comparing with stock behavior.
   Cover every hook, every stored value (save -> reload through the OS writer and reader, old files
   without the data) and edge cases. Tests needing the stock OS must skip when firmware/ is empty.

7. If any code runs in the audio interrupt, count the instructions it adds per 32-sample block in
   the emulator (as counted() in tests/test_cpu_budget.py), idle and worst case, and add a
   regression test for that cost. The stock OS already uses ~89 % of that interrupt: do nothing
   when idle and keep the worst case as low as possible. Report the numbers to me.

8. Add mods/<name>/mod.json with exactly {"title", "kind", "summary"} (kind "feature", or
   "machine" for a synth machine; summary one sentence of plain ASCII English) and
   mods/<name>/README.md: use on the device, how it works (hooks and addresses), tests, credits.
   Keep docs short and factual.

9. Build together with all other mods and check that it passes:
   python tools/build/build.py --stock firmware/<stock>.syx mods/<name> mods/splash mods/dual-mono \
     mods/master-comp mods/readable-values mods/perf-fx mods/fx3 -o out/test.syx

10. Run and fix until everything passes:
    python -m pytest
    cd web-builder && npm test && npm run build
    python tools/build/registry.py && git diff --exit-code docs/registry.md

11. Don't commit, push or open the pull request yourself. Prepare a pull request description for
    the `dev` branch: what the mod does, files added, resources claimed, test results (which tests
    ran with the stock OS), audio cost per block, what still needs testing on the device, credits
    and licenses of any third-party code. Then tell me to flash and test on the device before I submit.

Never post the mod or instructions on Elektronauts (forbidden there). If a rule conflicts with
what I ask, tell me instead of working around it.
