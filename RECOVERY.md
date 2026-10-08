# Recovery

The Syntakt's **bootstrap** (section 2) contains its own OS-upgrade menu. Our tools never modify it, so a mod that crashes at boot is recoverable.

## Normal case (OS still boots)

Flash the stock `.syx` with Elektron Transfer → *Drop* page. Works even if a mod misbehaves, as long as the OS starts.

## OS doesn't boot: MIDI DIN recovery

USB doesn't work from the startup menu — you need a MIDI interface with a 5-pin MIDI OUT.

1. MIDI OUT of the interface → **MIDI IN** of the Syntakt.
2. Hold **[FUNC]** while powering on → **STARTUP** menu.
3. **[TRIG 4]** → OS UPGRADE.
4. Elektron Transfer → SYSEX TRANSFER → **OS Upgrade via device startup menu** → send the stock `.syx` to the MIDI port.
5. Wait (tens of minutes at 31.25 kbit/s). The Syntakt restarts by itself.

Avoid **[TRIG 2]** (empty reset) and **[TRIG 3]** (factory reset): they erase data.

## Before your first flash

- Back up projects and sounds with Transfer.
- Do one dry run of the MIDI DIN procedure with the stock OS.
- Only flash files where `python tools/unpack/eft.py info <file>` reports `checksums : ok`.
