# firmware/ (locale, git-ignored)

Qui va l'OS **stock** della Syntakt, scaricato da te da elektron.se. Questa cartella è
esclusa da git: l'unico file versionato è questo README.

1. Scarica il Syntakt OS **1.41** dalla pagina di supporto/download Syntakt su elektron.se.
   Se la 1.41 non è più disponibile, scrivilo nel re-journal: la base del progetto è la 1.41.
2. Salvalo qui come `Syntakt_OS1.41.syx`.
3. Verifica:
   ```sh
   python tools/unpack/eft.py info firmware/Syntakt_OS1.41.syx
   ```
   Deve riconoscere il device "Syntakt" e riportare `checksums : ok`.

Non condividere questi file e non committarli: vedi [../docs/legal.md](../docs/legal.md).
