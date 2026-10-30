## Why SyntHack?

Until now, Syntakt hacks were one-off firmware files: each did one thing, and none could be combined with another.
SyntHack is one shared structure for all of them. Every mod is checked against the stock OS and against every other
mod, so you can pick the ones you want and use them together. You build your own OS from your own stock OS file, in
your browser: nothing is uploaded, and no firmware is distributed. To undo it, flash the stock OS.

> **Not affiliated with Elektron.** Modified firmware can make your device unusable and may void your warranty.
> Learn the recovery procedure before your first flash. Use at your own risk.

## What you need

**Supported OS:** Syntakt OS 1.42 (the current release on elektron.se). Everything on this page about "the stock OS"
means this version.

- An Elektron Syntakt and a USB cable.
- The stock OS file from [elektron.se](https://www.elektron.se/support-downloads/syntakt), unmodified.
- Elektron Transfer on your computer (from elektron.se).
- A desktop browser.
- For recovery, if the OS ever fails to boot: a MIDI interface with a 5-pin MIDI OUT.

## Build your OS

1. Download the stock OS from elektron.se.
2. In **Create your OS** on the home page, choose the `.syx` file (or drop it on the page). The page checks its SHA-256 fingerprint
   and refuses any other file, including an already modified one.
3. Pick your mods. Mods that others need (mod area, virtual parameters, kit storage) are added automatically.
   The boot splash is part of every build.
4. Optional: type your name to show it on the boot splash (letters, digits, `.` and `-`, up to 20 characters,
   shown in capitals).
5. Click **Build my OS**. A build takes 30 to 60 seconds.
6. Download `synthack.syx` and the **build report** (`.json`). Keep the report: it lists the stock OS, the mods and
   the fingerprint of your file, and it helps if you report a bug.

Every build runs the same checks as the command-line tool: the original bytes each mod expects, overlaps between
mods, protected sections, the boot decompression margin and a final section-by-section comparison. The same mods give
the same file, byte for byte.

## Flash

Before your first flash:

- Back up your projects and sounds with Transfer.
- Read the [recovery procedure](https://github.com/Angelo-politek/Synthack-OS/blob/main/RECOVERY.md) and, ideally,
  do one dry run of it with the stock OS.

Then:

1. Connect the Syntakt to your computer over USB.
2. Open Elektron Transfer and go to the **Drop** page.
3. Drop `synthack.syx` on it and wait until the update is finished. Don't power off during the update.
4. On the next boot, the SyntHack logo appears at the end of the official intro. Boot time is unchanged.

## Go back to the stock OS

Flash the stock `.syx` from elektron.se the same way (Transfer, **Drop** page). Projects and samples stay on the
device.

If the OS doesn't start at all, use the MIDI DIN procedure in
[RECOVERY.md](https://github.com/Angelo-politek/Synthack-OS/blob/main/RECOVERY.md). It uses the Syntakt's own
startup menu, which no mod ever modifies. Avoid **[TRIG 2]** and **[TRIG 3]** in that menu: they erase data.

## Bus compressor

A compressor on the **FX track bus**: it compresses together the tracks routed to the FX track. Tracks not routed
there are not affected. Route what you want compressed together (for example kick, snare and bass) to the FX track.

FX track → **SYN** page:

| Knob | Range |
|---|---|
| THR | threshold, −60 … 0 dB |
| ATK | attack, 0.1 … 100 ms |
| REL | release, 10 ms … 2 s |
| MUP | makeup gain, 0 … +24 dB |
| RAT | OFF, 1.5:1, 2:1, 3:1, 4:1, 6:1, 8:1, 16:1, 20:1 |
| GR | gain-reduction meter (read only): full bar = no reduction, down to −18 dB |
| COMP | ON/OFF for A/B comparison; keeps the settings. Not saved, starts ON |
| DRIVE | unchanged |

- **Saved:** per pattern, with the kit; globally when *SYN global* is on.
- Existing projects load with the compressor OFF.
- There is no dry/wet control: the compressor works on the analog VCAs.

## Dual mono input

Set **SETTINGS → AUDIO ROUTING → EXTERNAL IN** to **mono**: IN L and IN R become two separate mono inputs.

- **External Mixer** page = IN L: level, DEL, REV, FX3 sends.
- **IN R** page: 4th page of the **MIXER** tab (only in mono), with its own level and DEL, REV, FX3 sends.
- Each input goes to the delay, the reverb, FX3 and the FX track (FUNC+FX, trig 16), centered.
- **Saved:** with the kit. Kits from older versions start with the IN R sends at 0.
- In stereo, everything works as in the stock OS.

## Performance FX

Sequencer effects on keys 13–16, on **all tracks** (analog ones too). They replace the older beat-repeat mod.

1. Press **FUNC + 15** (trig modifier *Mod A*).
2. Hold key 13, 14, 15 or 16 to play its effect. Release to resume **in time**, where the pattern would have been.
   With several keys held, the last one pressed wins.

Set each key's effect in the Mod A setup page (M1–M4):

| Text | Effect |
|---|---|
| `1/16` `1/8` `3/16` `1/4` `1/2` `1BAR` | repeat the slice that contains the step just played |
| `R1/8` `R1/4` `R1/2` `RBAR` | the same slice backwards |
| `HALF` | half speed inside an 8-step slice |
| `--` | nothing |

- Defaults: 1/16, 1/8, R1/4, HALF. **Saved:** with the kit.
- FUNC + 13, 14 and 16 keep their stock modifiers. In keyboard mode, keys 13–16 stay notes.
- **Quantized retrig:** **QNT** in the Retrig setup page (FUNC + 13, slot D), OFF/ON, saved with the kit. With QNT on
  and the sequencer running, a retrig played with keys 13–16 starts on the next step of its track.
- No audio processing: no extra load on the audio CPU.

## Readable parameter values

Parameters show real units instead of 0–127: Hz for filters, ms and s for envelopes, dB for levels and sends, % for
sustain. It covers filters, envelopes, levels, sends, delay and reverb, on every track and on the FX track.

- Values are computed from the same data the sound engine uses. Analog filter values were measured on the device.
- Analog amp envelope times start with `~`: they are estimates (±10–20 %).
- Still shown as numbers: filter envelope and BASE/WDTH on analog tracks and the FX track, LFOs, RESO, and parameters
  without a unit.
- Nothing is saved: it only changes the display.

## Third send FX

A third send effect next to delay and reverb: **chorus**, **flanger**, **phaser** or **crusher**.

- **SND3** on every track: **AMP page 1**, slot G, next to DEL and REV. PAN moves to AMP page 2, slot E. SND3 is saved
  per track, can be p-locked and is an LFO destination.
- **External input:** its own FX3 send on the External Mixer page.
- **FX3 page:** FX track → **REVERB** tab, press it again for page 2. TYPE picks the effect; the next knobs change
  with it:

| TYPE | Knobs |
|---|---|
| CHOR | SPD, DEP, TIME, FDBK, WID |
| FLNG | SPD, DEP, TIME, FDBK (bipolar), WID |
| PHSR | SPD, DEP, FREQ, FDBK (bipolar), WID |
| CRSH | SRR, BITS, DRV |

- **DEL** and **REV** on the FX3 page send the effect into the delay and the reverb.
- Changing TYPE resets the effect knobs to that type's starting values; CRSH starts neutral.
- **Routing:** the effect returns to the main output, or to the FX track with **trig 13** on the ROUTING screen
  (FUNC+FX), next to delay (14) and reverb (15).
- **Saved:** with the kit, per pattern, like delay and reverb. Older projects load with the default values.
- It uses CPU only while tracks send to it. See [Known issues](#known-issues).

## Boot splash

The SyntHack logo and version appear at the end of the official intro, with your name if you entered one. Boot time is
unchanged. It is part of every build, so you can always tell which OS is running.

## Known issues

- **UI lag with heavy Third send FX use.** Many tracks sent to FX3 with high feedback (chorus, phaser) load the audio
  CPU heavily and the screen and keys can lag. The stock OS already uses about 89 % of that CPU at rest. This is being
  optimized. Until then, send fewer tracks or lower the feedback.
- **Bus compressor and *global* external mixer.** Toggling *global* for the external input mixer also copies the
  compressor settings (they share that kit block).
- **v0.8.0 and earlier: projects with SP TWINSHOT samples could crash at boot**
  ([#4](https://github.com/Angelo-politek/Synthack-OS/issues/4)). Fixed in v0.8.1. If you still run one of those
  builds, flash the stock OS (projects and samples are not affected), then build a current version.

## FAQ

### Is it safe?

Every mod is tested in an emulator against the original OS code and on real hardware before release, and every build
is checked before you download it. Still, this is unofficial firmware: back up first and learn the recovery
procedure. No mod touches the Syntakt's startup menu (bootstrap), so the MIDI DIN recovery stays available.

### What about my warranty?

Modified firmware may void it. SyntHack is not affiliated with, endorsed or supported by Elektron. Don't ask Elektron
support for help with a modded OS; flash the stock OS first.

### Which OS version do I need?

The one named under [What you need](#what-you-need), downloaded from elektron.se and unmodified. The builder checks its
fingerprint and refuses any other file.

### Can I share my built file?

Please don't: it contains Elektron's OS. Share your list of mods instead; anyone can build the same file from their
own stock OS. Neither the mods nor built files are for sale.

### Why isn't SyntHack on Elektronauts?

Posting modified firmware or instructions is forbidden there. Please use
[GitHub](https://github.com/Angelo-politek/Synthack-OS) for questions, bugs and ideas.

### How do I report a bug?

Open a [bug report](https://github.com/Angelo-politek/Synthack-OS/issues/new?template=bug_report.md) on GitHub. Attach
the build report (`.json`) and write the steps to reproduce the problem. Check first whether the problem also happens
with the stock OS.
