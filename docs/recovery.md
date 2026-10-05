# Recovery — come riportare la Syntakt all'OS stock

> **Regola:** nessun flash di firmware modificato finché la "prova a secco" in fondo a questa
> pagina non è stata completata e registrata.

## Perché funziona (in breve)

Il `.syx` della Syntakt contiene diverse sezioni. Una di queste (id 2, chiamata
**bootstrap** da `elektron-firmware-tool`) contiene il codice del menu di avvio: nelle sue
stringhe compaiono "BOOTSTRAP UPGRADE", "OS UPGRADE", "STARTUP MENU". È questo codice che ci
permette di reinstallare l'OS anche quando l'OS principale (sezione 3) non parte più.

Quindi:

- **Noi non modifichiamo MAI la sezione 2 (bootstrap) né la sezione 6 (boot).** Il nostro
  tooling deve rifiutarsi di farlo.
- Finché il bootstrap è intatto, un OS che crasha all'avvio è un problema recuperabile, non un
  brick.

Si recupera via **MIDI DIN** (il connettore tondo a 5 pin) e non via USB perché il
recupero deve funzionare anche quando l'OS è rotto. Il manuale ufficiale lo dice
esplicitamente: *"USB MIDI transfer is not possible when upgrading the OS from the STARTUP
menu"* (Syntakt User Manual OS 1.30, §15.4). Il nostro sospetto è che l'USB sia gestito
dall'OS principale, mentre la ricezione via MIDI DIN vive nel bootstrap. È un'ipotesi
coerente con quanto sopra, ma non verificata.

## Cosa serve

| Cosa | Stato | Note |
|---|---|---|
| Interfaccia con **MIDI OUT a 5 pin** | ✅ Behringer UMC404HD | ha MIDI IN/OUT DIN; verificare driver Windows aggiornati |
| Cavo MIDI DIN 5 pin | da verificare | MIDI OUT interfaccia → **MIDI IN** Syntakt |
| OS stock `Syntakt_OS1.41.syx` | da scaricare | da elektron.se, tenerlo in `firmware/` (git-ignored) |
| Programma per inviare SysEx | ✅ confermato | **Elektron Transfer**, pagina SYSEX TRANSFER → "OS Upgrade via device startup menu" (manuale §15.4). Ripiego: MIDI-OX |
| Backup di progetti e sound | da fare | con Elektron Transfer, prima di qualunque flash |

## Procedura ufficiale (Syntakt User Manual OS 1.30, §15 "Startup menu", pag. 81)

> ✅ Verificata sul manuale ufficiale. Il manuale è dell'OS 1.30: alla prova a secco
> controlla che le voci di Transfer abbiano ancora gli stessi nomi.

1. Scarica l'OS stock da elektron.se (`firmware/Syntakt_OS1.41.syx`).
2. Collega la porta **MIDI IN** della Syntakt alla porta **MIDI OUT** dell'interfaccia MIDI del PC.
3. Syntakt spenta: tieni premuto **[FUNC]** e accendila. Compare il menu **STARTUP**.
4. Premi **[TRIG 4]** per entrare in modalità **OS UPGRADE**.
5. Apri **Elektron Transfer**. Nella pagina CONNECTION clicca "go to the SYSEX TRANSFER page".
6. Nella pagina SYSEX TRANSFER clicca **"OS Upgrade via device startup menu"** e segui le
   istruzioni a schermo, scegliendo come uscita la porta MIDI dell'interfaccia.
7. Attendi la fine. Può volerci parecchio: il MIDI DIN va a 31,25 kbit/s, quindi ~2,5 MB
   richiedono diversi minuti. A fine aggiornamento la Syntakt si riavvia da sola.
8. Controlla la versione dell'OS.

Altre voci del menu STARTUP (manuale §15): TRIG 1 = test mode, TRIG 2 = empty reset
(**cancella pattern e suoni**), TRIG 3 = factory reset (**sovrascrive progetto attivo e banchi
A–E**), TRIG 5 = esci. Attenzione a non premere 2 o 3 per sbaglio.

### Aggiornamento normale (OS funzionante, via USB)

Per confronto, a macchina funzionante l'OS si aggiorna via USB con Transfer: pagina DROP,
trascini il `.syx` e confermi con [YES] (manuale §14.8.5). La Syntakt è sempre pronta a
ricevere un OS via USB. Questa **non** è la strada di recupero, perché richiede che l'OS
principale funzioni.

### Se l'invio fallisce

- Molti driver/utility spezzano o accelerano troppo i SysEx grandi. In MIDI-OX aumenta la
  dimensione dei buffer e aggiungi un ritardo tra i pacchetti.
- Riprova: finché il bootstrap è intatto il menu OS UPGRADE resta disponibile.
- Niente hub USB passivi; cavo USB diretto per l'interfaccia.

## Cosa NON fare

- Non spegnere la Syntakt mentre scrive l'OS.
- Non flashare un `.syx` che `python tools/unpack/eft.py info` non dà con `checksums : ok`.
- Non flashare un `.syx` in cui sia cambiata la sezione 2 o la 6 (il tool `eft.py` lo blocca).
- Non usare per il recupero un `.syx` diverso dall'OS stock scaricato da elektron.se.

## Prova a secco (obbligatoria, prima del primo flash modificato)

Si fa **con l'OS stock**, cioè un normale reinstallo ufficiale: rischio minimo, ma ci
insegna la procedura quando ancora non serve.

- [ ] Backup progetti/sound con Transfer
- [x] Procedura verificata sul manuale ufficiale (OS 1.30, §15.4) e corretta qui sopra
- [ ] Reinstallo dell'OS stock via **MIDI DIN** riuscito
- [ ] Registrato qui sotto: data, interfaccia, programma usato, durata, problemi

### Registro delle prove

| Data | Interfaccia | Programma | OS inviato | Durata | Esito / note |
|---|---|---|---|---|---|
| | | | | | |
