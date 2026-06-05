# PassApp Versione 2 Moderna - Qt/PySide6

PassApp e ora un'app unica basata su Qt/PySide6. Il codice storico e stato archiviato in `legacy_tkinter/` solo per consultazione e non viene piu usato come applicazione ufficiale.

## Avvio
- `python main.py` avvia la versione moderna Qt/PySide6.
- `main_qt.py` resta come alias temporaneo e richiama lo stesso entrypoint.
- `AVVIA_PASSAPP.bat` avvia l'EXE in `dist\PassAppQt`; se l'EXE non esiste avvia la preparazione guidata.

## Moduli disponibili
- Dashboard operativa
- Pass Invalidi
- Segnalazioni Cittadini
- Sopralluoghi
- Accertamenti anagrafici
- Ospitalita Stranieri
- Report mensile
- Contatti utili
- Configurazione
- Diagnostica
- Storico modifiche/audit

## Prima installazione
1. Copia l'intera cartella su ogni PC, ad esempio sul Desktop o in Documenti.
2. Esegui `PREPARA_PC_E_CREA_EXE.bat`.
3. Lo script verifica Python, Git, requirements, aggiornamenti GitHub, test e crea l'EXE.
4. Segui le istruzioni a schermo e poi usa `AVVIA_PASSAPP.bat`.

## Utilizzo quotidiano
1. Avvia `AVVIA_PASSAPP.bat` oppure il collegamento creato sul Desktop.
2. Dal menu laterale scegli il modulo operativo.
3. I percorsi di rete, le scadenze e le cartelle PDF si configurano dalla pagina Configurazione o in `data/config.json`.
4. Nei moduli `Pass Invalidi` e `Ospitalita Stranieri` le nuove righe vengono prima salvate in una copia di lavoro: usa `Salva modifiche` per aggiornare il file Excel originale.

## Aggiornamenti
- All'avvio l'app controlla se su GitHub e disponibile una nuova versione.
- Se l'utente accetta, viene lanciato `AGGIORNA_RICREA_EXE_E_RIAVVIA.bat`.
- Lo script chiude l'app, aggiorna la repository, aggiorna i requirements, ricrea l'EXE e riavvia PassApp.
- Non copiare `data/users.json` tra PC diversi: l'admin viene legato al PC dove il file utenti viene creato.

## Autenticazione
- L'autenticazione e attualmente disattivata.
- Il codice e stato mantenuto in `core/auth.py` e `qt_app/login.py` per poterla riattivare rapidamente piu avanti.
- Con autenticazione disattivata, l'app si apre direttamente e la sezione Configurazione resta accessibile.

## Note tecniche
- La UI ufficiale richiede `PySide6`.
- La build PyInstaller usa `main.py` e produce l'eseguibile Qt.
- I servizi condivisi sono in `core/`; le pagine moderne sono in `qt_app/`.
- I PDF delle segnalazioni e dei sopralluoghi richiedono Microsoft Word Desktop.
- Il salvataggio modifiche su file `.xls` usa Microsoft Excel Desktop tramite automazione COM.
- I log applicativi vengono salvati in `data/passapp.log`.

## Problemi comuni
**"Nessun file trovato"** -> verifica che il percorso di rete configurato in `data/config.json` sia disponibile.

**"Python non trovato"** -> reinstalla Python e abilita l'opzione `Add Python to PATH`.

**File non aggiornato** -> usa il pulsante `Aggiorna` nel modulo interessato.
