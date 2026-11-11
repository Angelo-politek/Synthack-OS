# sample-manager

A **SAMPLES** row in the settings menu: the project's list of [long samples](../long-samples), on the device.

| Control | Action |
|---|---|
| Settings menu, SAMPLES, `YES` | Open the list: position, name, length |
| `UP` / `DOWN`, any encoder | Move |
| `YES` | The active track (1-8) gets the SAMPLER with this sample. A track that is a SAMPLER keeps its settings |
| `FUNC` + `UP` / `DOWN` | Move the sample up or down in the list |
| `FUNC` + `NO`, twice | Delete the sample from the Syntakt |
| `NO` | Close |

- Saved: the order, with the project (long-samples' list). A deleted sample is gone from the Syntakt's storage for every project.
- Audio cost per block: none.
- Tested on the device: no.

`[!]` Back up with the Samples page of the site before deleting: there is no undo.

`[!]` Moving a sample changes what tracks play: `SAMP` is a position in the list, and two positions change places. A deleted sample leaves its position empty, so the others keep theirs.

`[!]` Not here: rename, tags, preview, the stock slots (use Transfer and the Samples page of the site).

## How it works

- The row is added by [about](../about), which owns the settings menu's hook: it reads the four callbacks at `smgr_row`.
- The list is drawn over the frame while it is open and takes every key but transport, through [sfcore](../sfcore)'s draw, key, encoder and tick events (module slot 6).
- List and storage are long-samples': `ls_table`, `ls_names`, `ls_id_at`, `ls_swap`, `ls_forget`, and Synfact's `core_hzfs_remove` (GSM1980 and contributors, GPL-2.0-or-later).
- The track gets the SAMPLER as from the [recorder](../recorder): the machine menu's value for ONESHOT, then `SAMP` through the Sound's setter.

Tests: `tests/test_sample_manager.py`. Space: [claims.json](claims.json).
