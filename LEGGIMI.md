# PassApp Suite Ufficio Servizi

## Contenuto cartella
- `main.py` -> programma principale con menu moduli
- `pass_invalidi.py` -> modulo Pass Invalidi
- `segnalazioni.py` -> modulo Segnalazioni Cittadini
- `ospitalita_stranieri.py` -> modulo Ospitalita Stranieri
- `data/config.json` -> configurazione centralizzata di percorsi, scadenze, output e UI
- `INSTALLA.bat` -> installazione dipendenze e collegamento desktop
- `SETUP_PYTHON_E_INSTALLA.bat` -> verifica Python e avvio installazione completa
- `Avvia App.bat` -> avvio rapido della suite

## Prima installazione
1. Copia l'intera cartella su ogni PC, ad esempio sul Desktop o in Documenti.
2. Esegui `SETUP_PYTHON_E_INSTALLA.bat` se devi verificare o installare Python.
3. In alternativa, se Python e gia presente, esegui direttamente `INSTALLA.bat`.
4. Segui le istruzioni a schermo.

## Utilizzo quotidiano
1. Avvia `Avvia App.bat` oppure il collegamento creato sul Desktop.
2. Dal menu principale scegli il modulo operativo.
3. I percorsi di rete, i giorni di preavviso scadenza e le cartelle PDF si configurano in `data/config.json`.
4. Nei moduli `Pass Invalidi` e `Ospitalita Stranieri` le nuove righe vengono prima salvate in una copia di lavoro: usa il pulsante `SALVA MODIFICHE` per aggiornare il file Excel originale.

## Configurazione
Il file `data/config.json` contiene:
- percorsi di rete dei moduli
- pattern di ricerca dei file Excel
- giorni di preavviso per i pass in scadenza
- cartelle dati, log e output PDF
- nome suite, titoli e opzioni UI di base

## Note tecniche
- Il disco di rete configurato deve essere raggiungibile dal PC.
- I log applicativi vengono salvati in `data/passapp.log`.
- I PDF delle segnalazioni vengono proposti nella cartella configurata in `documenti/segnalazioni_pdf`.
- L'esportazione PDF delle segnalazioni richiede Microsoft Word Desktop installato sul PC.
- Il salvataggio modifiche su file `.xls` usa Microsoft Excel Desktop (automazione COM).
- Gli script di avvio/installazione usano automaticamente `python` oppure `py -3`.
- Nessun dato viene inviato online: tutto resta locale.

## Problemi comuni
**"Nessun file trovato"** -> verifica che il percorso di rete configurato in `data/config.json` sia disponibile.

**"Python non trovato"** -> reinstalla Python e abilita l'opzione `Add Python to PATH`.

**File non aggiornato** -> usa il pulsante `Aggiorna` nel modulo interessato.
