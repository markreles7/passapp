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
- Assistente Operativo (ChatGPT)
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
- Le funzioni IA usano esclusivamente ChatGPT con accesso OAuth ufficiale; non richiedono API key.
- Ogni comando dell'Assistente Operativo viene mostrato in anteprima e non modifica dati senza conferma dell'operatore.

## Collegare ChatGPT
1. Apri `Configurazione` e premi `Continue with ChatGPT`.
2. Nel browser ufficiale accedi al tuo account e autorizza PassApp a usare il piano ChatGPT.
3. Premi `Verifica connessione ChatGPT` per caricare i modelli disponibili per l'account.
4. Scegli un modello (oppure lascia la selezione automatica) e salva la configurazione.
5. Usa l'Assistente Operativo e la generazione delle bozze nei moduli Segnalazioni e Sopralluoghi.

L'integrazione segue https://developers.openai.com/siwc/token-sharing-open-source per app locali.
La disponibilita dipende dall'idoneita dell'account e dell'app. L'utilizzo consuma i limiti condivisi
Plus/Pro, non aggiunge una quota separata. `Gestisci utilizzo` apre le impostazioni di ChatGPT.
Il login non concede accesso alle conversazioni o alle memorie di ChatGPT.

Le credenziali sono cifrate tramite Windows DPAPI per l'utente corrente, in
`%LOCALAPPDATA%\PassApp\ChatGPT`, fuori dalla cartella condivisa. Il login del gestionale resta
separato dall'account ChatGPT. `Scollega ChatGPT` elimina i token locali; per revocare l'autorizzazione
usa ChatGPT > Impostazioni > Sicurezza e accesso > Sign in with ChatGPT.
Non copiare questa cartella di credenziali tra PC o utenti.

I dati inseriti nelle richieste vengono inviati a OpenAI. Il contenuto generato resta una bozza
che l'operatore deve verificare. Se una richiesta fallisce, l'errore viene mostrato: il gestionale
non spaccia un testo standard per una risposta ChatGPT. Disattivando `Bozze documenti con ChatGPT`
si usa la compilazione standard senza IA. Le didascalie fotografiche restano manuali.
Le vecchie impostazioni LM Studio/Gemini non vengono usate. Non serve installare modelli locali.
Dopo aggiornamento dei sorgenti, ricrea l'EXE per aggiornare anche l'app avviata dal file `.bat`.
Su questo PC l'EXE e gia pronto in `build/chatgpt-release/PassAppQt`.
Gli eseguibili non sono inclusi nel repository GitHub. Per ricreare questa versione,
con l'ambiente `.venv` preparato, esegui dalla cartella del progetto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath build/chatgpt-release --workpath build/chatgpt-work PassAppQt.spec
```

Chiudi PassApp ed esegui `INSTALLA_CHATGPT.bat`. L'installatore crea una copia della versione
precedente, aggiorna l'eseguibile abituale e conserva dati, configurazione e modelli di documento.

## Problemi comuni
**"Nessun file trovato"** -> verifica che il percorso di rete configurato in `data/config.json` sia disponibile.

**"Python non trovato"** -> reinstalla Python e abilita l'opzione `Add Python to PATH`.

**File non aggiornato** -> usa il pulsante `Aggiorna` nel modulo interessato.
