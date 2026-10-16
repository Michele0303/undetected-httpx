# Confronto registrato dal vivo con VHS

Queste GIF mostrano **i due binari in esecuzione**, con richieste nuove ai siti. Il 16 ottobre 2026, fra le 23:54 e le 23:55 Europe/Rome, httpx ha ricevuto cinque `403` e undetected-httpx cinque `200` sugli URL scelti.

[Video affiancato](comparison.mp4) · [Fotogramma finale](comparison-poster.png) · [Metadata dell'acquisizione](capture/metadata.json)

| httpx v1.12.0 | undetected-httpx 2.0 |
|---|---|
| ![Esecuzione reale di httpx](capture/upstream/httpx.gif) | ![Esecuzione reale di undetected-httpx](capture/fork/undetected-httpx.gif) |

## Le risposte effettive

| URL | httpx | undetected-httpx | Titolo nella risposta salvata dalla v2 |
|---|---:|---:|---|
| `https://ir.tripadvisor.com/` | 403 | 200 | Investor Relations \| Tripadvisor |
| `https://openai.com/` | 403 | 200 | OpenAI \| Research & Deployment |
| `https://platform.openai.com/` | 403 | 200 | OpenAI Platform |
| `https://www.adobe.com/` | 403 | 200 | Adobe: Creative, marketing and document management solutions |
| `https://www.npmjs.com/` | 403 | 200 | npm \| Home |

Abbiamo scelto questi URL perché il benchmark precedente mostrava differenze favorevoli alla v2. Le nuove esecuzioni hanno confermato gli status; non abbiamo sostituito, ordinato o eliminato righe nell'animazione. L'ordine visualizzato è quello prodotto dai programmi.

I titoli della v2 non mostrano indicatori noti di challenge. Questo campione selezionato non misura una percentuale generale di successo, e `200` non garantisce che tutte le funzionalità della pagina siano disponibili. Il [confronto completo su 96 host](../../benchmarks/2026-10-16/README.md) documenta anche blocchi residui e challenge con status `200`.

## Come abbiamo registrato

VHS **0.12.1** apre un terminale e digita i comandi seguenti:

```sh
httpx -l list.txt -sc -silent -config demo.yml
undetected-httpx -l list.txt -sc -silent -config demo.yml
```

I nomi nel `PATH` puntano ai binari reali tramite symlink; non sono wrapper che stampano risultati preparati. Il recorder conserva gli hash dei binari, il comando, la configurazione, gli orari e l'exit code dei due processi. I binari sono gli stessi usati nel benchmark precedente.

Entrambi leggono lo stesso [demo.yml](demo.yml): User-Agent Chrome 155 esplicito, un thread, tre probe iniziali al secondo, timeout 12 secondi, zero retry, nessun follow dei redirect, lettura massima 2 MiB e salvataggio delle risposte. HOME, XDG e ambiente sono isolati; non ereditiamo proxy, credenziali o cookie personali.

Prima delle richieste pubbliche, un server su localhost verifica la configurazione dei binari reali: sei richieste per lato, User-Agent identico, rate limit e salvataggio delle risposte. Durante la registrazione, `Wait` attende il ritorno del prompt e mantiene il terminale visibile per altri sei secondi. Entrambi i binari e i due processi VHS terminano con exit code 0.

I file sono in [capture/upstream](capture/upstream) e [capture/fork](capture/fork): GIF, MP4, schermata testuale `terminal.ascii`, `results.txt`, configurazione, tape e risposte HTTP. Gli indici delle risposte associano i file agli URL. I metadata conservano gli hash dei file.

Le risposte HTTP pubblicate omettono cookie e token di sessione restituiti dai siti. Il [manifest delle redazioni](redaction-manifest.json) riporta campi e hash prima e dopo la rimozione. GIF, video, output del terminale e risultati restano quelli registrati.

L'MP4 affiancato aggiunge i nomi dei programmi e una didascalia. Mantiene la velocità originale di entrambe le registrazioni e prolunga soltanto l'ultimo fotogramma della più corta. Non è un confronto di velocità: i programmi sono stati eseguiti in sequenza e i comandi hanno lunghezze diverse.

## Scelte visive

VHS non impone uno standard grafico. La [guida ufficiale](https://github.com/charmbracelet/vhs#vhs-command-reference) documenta dimensioni, font, margini, bordi, tempi di digitazione, `Wait` e velocità di riproduzione; il [demo ufficiale](https://github.com/charmbracelet/vhs/blob/main/examples/demo.tape) offre un esempio minimo. Per questa demo abbiamo scelto:

- Prompt `❯`, senza versione della shell, nome utente o percorso personale.
- Font Menlo da 28 px su un terminale da 1200 × 440 px, così il comando resta su una riga.
- Margini da 16 px, padding da 36 px, bordi arrotondati e un tema scuro coerente nelle due finestre.
- Colori prodotti dai tool: `403` rosa e `200` verde. Nessuna colorazione artificiale degli esiti.
- 25 fps, digitazione da 25 ms per carattere, riproduzione a velocità 1× e pausa finale di sei secondi.

Per il README le due GIF permettono la riproduzione automatica; per condivisione e presentazioni l'MP4 offre testo più nitido e controlli di riproduzione. I file `.tape` rendono il processo modificabile e ripetibile.

## Ripetere la registrazione

Installare VHS, ffmpeg e ttyd. Su macOS:

```sh
brew install vhs
```

Occorrono `bin/httpx-upstream-v1.12.0` e `bin/undetected-httpx`; le [istruzioni del benchmark](../../benchmarks/2026-10-16/README.md#metodo-riproduzione-e-correzioni) spiegano come compilarli. Dalla root del repository, verificare la configurazione senza traffico pubblico:

```sh
python3 scripts/record_comparison_demo.py --preflight-only
```

Per registrare nuove richieste, scegliere una cartella che non esiste:

```sh
python3 scripts/record_comparison_demo.py \
  --output docs/demos/v2-live/capture-new
python3 scripts/compose_live_demo.py \
  --capture docs/demos/v2-live/capture-new \
  --output docs/demos/v2-live/export-new
```

La composizione richiede anche Pillow. Su Linux impostare un font disponibile nel tape e passare `--font` al compositore. Il recorder rifiuta di sovrascrivere una cattura esistente. Prima di pubblicare una nuova acquisizione, controllare le risposte salvate e rimuovere eventuali IP del client, cookie e token di sessione.

## Tentativi di preparazione

Durante la preparazione abbiamo corretto due errori di parsing del tape e un timeout nell'attesa del prompt. Il tentativo con timeout aveva già eseguito httpx e aggiunto cinque richieste pubbliche rispetto alle dieci mostrate. Dopo la correzione in `Wait+Line /^❯$/` abbiamo registrato entrambi i video. Il repository conserva solo le acquisizioni complete.

La cronologia della v1 contiene le GIF ma non il registratore o i tape originali: VHS ricrea il formato, senza poter confermare quale software fosse stato usato allora.
