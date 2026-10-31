# Recovery

The Syntakt's **bootstrap** (section 2) has its own OS-upgrade menu. Our tools never modify it. A mod that crashes at boot is recoverable.

## OS still boots

1. Open Elektron Transfer. Go to the **Drop** page.
2. Drop the stock `.syx`.

This works even if a mod misbehaves, as long as the OS starts.

## OS doesn't boot: MIDI DIN

USB doesn't work from the startup menu. You need a MIDI interface with a 5-pin MIDI OUT.

1. Connect the interface's MIDI OUT to the Syntakt's **MIDI IN**.
2. Hold **[FUNC]** while you power on. The **STARTUP** menu opens.
3. Press **[TRIG 4]**: OS UPGRADE.
4. In Elektron Transfer, open SYSEX TRANSFER → **OS Upgrade via device startup menu**. Send the stock `.syx` to the MIDI port.
5. Wait. It takes tens of minutes at 31.25 kbit/s. The Syntakt restarts by itself.

`[!]` Avoid **[TRIG 2]** (empty reset) and **[TRIG 3]** (factory reset). They erase data.

## Before your first flash

1. Back up projects and sounds with Transfer.
2. Do one dry run of the MIDI DIN procedure with the stock OS.
3. Flash only files where `python tools/unpack/eft.py info <file>` reports `checksums : ok`.
