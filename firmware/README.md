# firmware/

Local only. Git ignores this folder.

1. Download the **stock** Syntakt OS 1.42 from elektron.se.
2. Save it here as `Syntakt_OS1.42.syx`.
3. Check it:
   ```sh
   python tools/unpack/eft.py info firmware/Syntakt_OS1.42.syx      # must say Syntakt, checksums : ok
   ```

Expected SHA-256: `ded3c59fdb909eb9e2c3307b30a486452c8fa6947b12c14e0ce35a187b7f37c1`.

`[!]` Never commit or share these files. See [LEGAL.md](../LEGAL.md).
