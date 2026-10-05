# Toolchain

Ambiente di riferimento: **Windows 11 + WSL (Ubuntu 24.04)**. Il codice C (tool di unpack,
cross-compiler) si compila in WSL; Python, Ghidra e Node girano su Windows.

## 1. elektron-firmware-tool (unpack/repack)

```sh
# da un terminale WSL, nella root del repo
bash tools/unpack/setup_eft.sh
```

Lo script clona il tool in `third_party/` (git-ignored), si posiziona su un commit fissato,
così tutti usano la stessa versione, e lo compila con `make`. Il wrapper
`tools/unpack/eft.py` lo trova da solo: da Windows lo lancia tramite `wsl.exe`, su Linux
direttamente. Per usare un binario diverso imposta la variabile d'ambiente `EFT_BIN`.

## 2. Ghidra (passo passo, Windows)

Ghidra è il disassemblatore/decompilatore open source della NSA: trasforma il codice
macchina in assembly leggibile e in pseudo-C. Supporta i ColdFire.

### 2.1 Installa il JDK 21

Ghidra **12.1.x** (stabile) richiede **Java 21 64-bit (JDK)**. Il Java 17 già presente sul
PC non basta. Le versioni future (13.x) chiederanno il JDK 25.

1. Vai su <https://adoptium.net/temurin/releases/?version=21>.
2. Scegli **Windows / x64 / JDK / .msi** e scaricalo.
3. Durante l'installazione, nella schermata delle funzionalità attiva:
   - **Set JAVA_HOME variable** → "Will be installed on local hard drive"
   - **Add to PATH** (di solito già attivo)
4. Apri un **nuovo** PowerShell e verifica:
   ```powershell
   java -version      # deve dire 21.x
   echo $env:JAVA_HOME
   ```
   Il Java 17 può restare installato: vince quello che compare prima nel PATH, e Ghidra
   comunque usa quello che gli indichi.

### 2.2 Scarica Ghidra

1. Vai su <https://github.com/NationalSecurityAgency/ghidra/releases>.
2. Sotto la release **Ghidra 12.1.4** → **Assets**, scarica lo zip
   `ghidra_12.1.4_PUBLIC_<data>.zip` (non i "Source code").
3. (Consigliato) verifica l'hash SHA-256 indicato nella release:
   ```powershell
   Get-FileHash .\ghidra_12.1.4_PUBLIC_*.zip -Algorithm SHA256
   ```
4. Estrai lo zip in una cartella **senza spazi** e **fuori da questo repo**, per esempio
   `C:\Tools\ghidra_12.1.4_PUBLIC`. Non serve un installer né i diritti di amministratore.

### 2.3 Primo avvio

1. Doppio clic su `C:\Tools\ghidra_12.1.4_PUBLIC\ghidraRun.bat`.
2. Se chiede il percorso del JDK, inserisci la cartella che **contiene** `bin`, per esempio
   `C:\Program Files\Eclipse Adoptium\jdk-21.x.x-hotspot`.
3. Accetta la licenza. (Facoltativo) crea un collegamento a `ghidraRun.bat` sul desktop.

### 2.4 Progetto Syntakt (quando avremo le sezioni estratte)

Il progetto Ghidra contiene il firmware disassemblato, quindi **non va mai nel repo**.
Tienilo in `C:\Users\<te>\ghidra-projects\`.

1. `File → New Project → Non-Shared Project` → cartella `ghidra-projects`, nome `syntakt-1.41`.
2. `File → Import File` → la sezione estratta (es. `unpacked/1.41/section_7_blob.raw`).
3. Nel dialogo di import:
   - **Format:** `Raw Binary` (le sezioni non hanno un header ELF che dica a Ghidra cosa sono)
   - **Language:** `68000:BE:32:Coldfire` (big-endian, 32 bit, variante ColdFire)
   - **Options… → Base Address:** `40000400`, sia per la sezione 7 sia per la 3 (verificato con
     un test statistico sui salti assoluti, vedi re-journal). Se i salti puntassero nel vuoto,
     l'indirizzo è sbagliato.
4. Alla domanda "Analyze now?" → **Yes**, opzioni di default.

> **Nota EMAC.** Il motore audio usa le istruzioni dell'unità EMAC (multiply-accumulate). Il
> linguaggio ColdFire di serie di Ghidra potrebbe non decodificarle: in quel caso vedrai byte
> marcati come "bad instruction" o lasciati non disassemblati. È atteso. digiemu offre
> un'estensione Ghidra (`tools/ghidra/ColdfireEMAC`, GPL) che si può installare **localmente**,
> senza copiarla nel repo, se ci servirà.

Le scoperte vanno annotate in [re-journal.md](re-journal.md), con parole nostre e senza incollare
disassemblato.

## 3. Cross-compiler ColdFire (più avanti, Fase 1)

In WSL:

```sh
sudo apt update
sudo apt install gcc-m68k-linux-gnu binutils-m68k-linux-gnu
m68k-linux-gnu-gcc --version
```

Ubuntu non distribuisce un `m68k-elf-gcc` "bare-metal" già pronto. Per il codice delle mod
va bene anche il compilatore `m68k-linux-gnu`, usato in modalità freestanding
(`-ffreestanding -nostdlib`) e con un nostro linker script. Il flag `-mcpu=…` lo sceglieremo
quando avremo identificato il modello esatto del ColdFire del motore audio (vedi
[hardware-notes.md](hardware-notes.md)).

## 4. Hook anti-firmware

Una volta per clone:

```sh
git config core.hooksPath tools/hooks
```
