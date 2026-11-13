# sample-manager

A **SAMPLES** row in the settings menu: the project's list of [long samples](../long-samples), on the device.

| Control | Action |
|---|---|
| Settings menu, SAMPLES, `YES` | Open the list: position, name, tag, length |
| `UP` / `DOWN`, any encoder | Choose a sample |
| `YES` | The active track (1-8) gets the SAMPLER with this sample |
| `FUNC` + `YES` | Listen to its first 3 s; again: stop |
| `RIGHT` | The sample's menu: ASSIGN, PLAY, RENAME, TAG, MOVE, DELETE. `LEFT` or `NO` closes it |
| `LEFT` | Show all the samples, or those with one tag |
| `FUNC` + `RIGHT`, `FUNC` + `UP` / `DOWN`, `FUNC` + `NO` twice | Shortcuts: rename, move, delete |
| `NO` | Close |

The screen follows the OS's lists: a header bar with the filter and the count, the chosen row inverted, a scroll bar, what the keys do at the bottom. The menu opens over the right side, as the OS's.

- Saved: the order, with the project (long-samples' list). Names and tags, with the sample, for every project. A deleted sample is gone from the Syntakt's storage for every project.
- Audio cost per block: a few instructions while nothing plays; the preview mixes 32 frames a block.
- Tested on the device: no.

`[!]` Back up with the Samples page of the site before deleting: there is no undo.

`[!]` Moving a sample changes what tracks play: `SAMP` is a position in the list, and two positions change places. A deleted sample leaves its position empty, so the others keep theirs.

`[!]` Not here: the stock slots (Transfer), adding samples and backups (the Samples page of the site).

`[!]` A tag is written when you leave the row or close the list. It is the low byte of the catalogue entry's `flags`, which nothing else uses: the site and Synfact's tool keep it.

## How it works

- The row is added by [about](../about), which owns the settings menu's hook: it reads the four callbacks at `smgr_row`.
- The list is drawn over the frame while it is open and takes every key but transport, through [sfcore](../sfcore)'s draw, key, encoder and tick events (module slot 6).
- List and storage are long-samples': `ls_table`, `ls_names`, `ls_id_at`, `ls_swap`, `ls_forget`, `ls_mmc_at`, Synfact's `core_hzfs_remove`, and `core_hzfs_update` (ours, at the end of `hzfs.c`: name and flags) (GSM1980 and contributors, GPL-2.0-or-later).
- The track gets the SAMPLER as from the [recorder](../recorder): the machine menu's value for ONESHOT, then `SAMP` through the Sound's setter.

Tests: `tests/test_sample_manager.py`. Space: [claims.json](claims.json).
- The preview reads the start of the file from the eMMC into the heap (UI task); the audio interrupt only mixes it into the preview bus, as the recorder's audition (sfcore's main-mix event).
