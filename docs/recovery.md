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
recupero
deve funzionare anche quando l'OS è rotto. L'USB della Syntakt è gestito in larga parte
dall'OS, mentre la ricezione via MIDI DIN nel menu di avvio è più semplice e indipendente.
*(Ipotesi ragionevole, da confermare: per ora la trattiamo come "la via sicura".)*

## Cosa serve

| Cosa | Stato | Note |
|---|---|---|
| Interfaccia con **MIDI OUT a 5 pin** | da recuperare | scheda Behringer dell'utente: verificare che abbia MIDI OUT e driver Windows funzionanti |
| Cavo MIDI DIN 5 pin | da verificare | MIDI OUT interfaccia → **MIDI IN** Syntakt |
| OS stock `Syntakt_OS1.41.syx` | da scaricare | da elektron.se, tenerlo in `firmware/` (git-ignored) |
| Programma per inviare SysEx | da scegliere | Elektron Transfer (se offre ancora l'invio "legacy" su DIN) oppure MIDI-OX / SysEx Librarian — **da verificare** |
| Backup di progetti e sound | da fare | con Elektron Transfer, prima di qualunque flash |

## Procedura (bozza — da confermare sul manuale ufficiale Syntakt)

> I passaggi qui sotto vengono dalla community, non da Elektron. Prima della prova a secco
> confrontali con il manuale utente ufficiale (sezione "Startup menu" / "OS upgrade") e
> correggi questa pagina.

1. Collega **MIDI OUT** dell'interfaccia → **MIDI IN** della Syntakt.
2. Syntakt spenta. Tieni premuto **[FUNC]** e accendi: compare il menu **STARTUP**.
3. Premi **[TRIG 4]** → "OS UPGRADE". La macchina si mette in attesa di dati SysEx.
4. Dal PC invia il `.syx` **stock** sulla porta MIDI dell'interfaccia
   (Transfer: modalità "Legacy OS Upgrade" su MIDI DIN — da verificare il nome esatto).
5. Attendi la fine (può volerci parecchio: il MIDI DIN va a 31.25 kbit/s). La Syntakt
   mostra l'avanzamento e poi chiede di riavviare.
6. Riavvia e controlla la versione dell'OS.

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
- [ ] Procedura verificata sul manuale ufficiale e corretta qui sopra
- [ ] Reinstallo dell'OS stock via **MIDI DIN** riuscito
- [ ] Registrato qui sotto: data, interfaccia, programma usato, durata, problemi

### Registro delle prove

| Data | Interfaccia | Programma | OS inviato | Durata | Esito / note |
|---|---|---|---|---|---|
| | | | | | |
