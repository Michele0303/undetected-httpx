# httpx vs undetected-httpx 2.0 — 16 ottobre 2026

La 2.0 riceve meno `403` nel campione: **1 contro 8 a parità di User-Agent**. Seguendo i redirect ottiene **93 risposte 2xx contro 82**, ma due sono pagine di verifica con status `200`. Il risultato sostiene l'utilità del trasporto browser su questi siti; non dimostra che le richieste siano indistinguibili da un browser reale.

[Apri il report interattivo](index.html) per cercare un host, filtrare le differenze e confrontare titoli, redirect, hash, errori e tempi. Il file funziona anche senza server o connessione Internet. I dati collegati richiedono la cartella del benchmark accanto al file.

## Campione e risultati

Abbiamo interrogato **96 URL su 96 host distinti**, divisi in **32 gruppi di siti**: homepage e sottodomini pubblici di documentazione, assistenza, community e stato del servizio. La [lista completa](targets.csv) è esplicita; non abbiamo enumerato sottodomini né scansionato porte.

Le cinque esecuzioni valide sono avvenute fra **23:20:45 e 23:29:13, Europe/Rome**, il 16 ottobre 2026. Ogni esecuzione comprende 96 osservazioni per strumento: **960 osservazioni complessive**, tutte con una risposta HTTP e processi terminati con exit code 0. Nessun output mancante, duplicato, malformato o non associato all'input. Questo non è il numero totale di richieste HTTP: i redirect possono aggiungerne.

Nella tabella ogni coppia è **upstream / fork**. Le pagine di verifica sono rilevate con un'euristica su header e titoli; il conteggio comprende anche pagine di blocco e può ometterne altre.

| Esecuzione | Ordine | HTTP 2xx | HTTP 403 | HTTP 406 | Pagine di verifica/blocco* | Status diversi |
|---|---|---:|---:|---:|---:|---:|
| [Baseline AB](baseline-ab-verified/report.md) | upstream → fork | 60 / 64 | 6 / 1 | 2 / 0 | 4 / 2 | 9 |
| [Baseline BA](baseline-ba-verified/report.md) | fork → upstream | 59 / 64 | 7 / 1 | 3 / 0 | 5 / 2 | 11 |
| [User-Agent uguale](matched-verified/report.md) | upstream → fork | 62 / 64 | 8 / 1 | 0 / 0 | 6 / 2 | 10 |
| [Redirect](redirects-verified/report.md) | fork → upstream | 82 / 93 | 9 / 2 | 4 / 0 | 7 / 3 | 11 |
| [Controllo nativo](native-control-verified/report.md) | upstream → fork | 61 / 61 | 8 / 9 | 0 / 0 | 6 / 7 | 1 |

La baseline usa uno User-Agent upstream fisso e il profilo `chrome-latest` del fork. Il test con User-Agent uguale imposta esplicitamente Chrome 155 su entrambi. Il controllo nativo usa lo stesso User-Agent e `-native-http` nel fork. Soltanto la prova Redirect segue i redirect, fino a due passaggi: in httpx `-maxr 3` conta anche la richiesta iniziale.

## Differenze che si ripetono

Otto URL mostrano la stessa differenza di status nei due ordini della baseline:

| Host | Upstream | Fork | Riscontro nel contenuto o nella destinazione |
|---|---:|---:|---|
| `openai.com` | 403 | 200 | Titolo OpenAI; stessa differenza anche con User-Agent uguale. |
| `platform.openai.com` | 403 | 200 | Titolo OpenAI Platform; stessa differenza con User-Agent uguale. |
| `www.npmjs.com` | 403 | 200 | Da “Just a moment...” a “npm \| Home”; stessa differenza con User-Agent uguale. |
| `ir.tripadvisor.com` | 403 | 200 | Da “Access Denied” a “Investor Relations \| Tripadvisor”; stessa differenza con User-Agent uguale. |
| `help.openai.com` | 403 | 302 | Nel test Redirect il fork arriva a `200`, “OpenAI Help Center”. |
| `developer.paypal.com` | 406 | 200 | Titolo PayPal Developer. Con User-Agent uguale entrambi rispondono `200`: non attribuire questo caso al solo TLS. |
| `support.mozilla.org` | 406 | 200 | Il fork mostra **“Client Challenge”**. Con User-Agent uguale entrambi ricevono questa pagina: non è accesso al contenuto. |
| `www.shopify.com` | 200 | 302 | Cambia la localizzazione; nel test Redirect entrambi arrivano a `200`. |

Tre URL cambiano status fra AB e BA: Mozilla homepage, Shopify Help e Booking. Anche con il trasporto nativo su entrambi, Shopify Help risponde `302` a upstream e `403` al fork. Questo residuo dimostra perché una differenza osservata una sola volta non basta ad attribuire la causa a HTTPcloak.

## Cosa emerge seguendo i redirect

Nel test Redirect, gli 11 passaggi da non-2xx a 2xx riguardano OpenAI homepage, Help e Platform; Mozilla homepage e Support; npm; Discord Support; Shopify Help; PayPal homepage e Developer; Tripadvisor Investor Relations. Dieci hanno un titolo senza indicatori di challenge nell'euristica, mentre Mozilla Support resta una challenge. Non abbiamo verificato login, funzionalità JavaScript o equivalenza completa delle pagine.

Restano alcuni casi da tenere distinti:

- **Reddit:** il fork riceve `200` con “Reddit - Prove your humanity” in tutte le quattro prove browser. Upstream riceve anch'esso `200`, ma il solo titolo generico non dimostra che il contenuto sia utilizzabile. Il conteggio degli status non rivela questa differenza.
- **Mozilla Support:** `200` “Client Challenge” nel fork; non va contato come superamento della verifica.
- **Stack Overflow:** entrambi arrivano a `/questions` e ricevono `403`, “Just a moment...”.
- **Tripadvisor homepage:** entrambi ricevono `403`; il miglioramento sul sottodominio Investor Relations non vale per la homepage.
- **HackerOne Support:** entrambi restano a `302` al limite dei redirect. Non è un errore del processo né una prova di blocco.
- **Microsoft, User-Agent uguale:** upstream riceve `200` con “Your request has been blocked”, il fork `302`. Interpretare il passaggio 200 → 302 come regressione sarebbe fuorviante.
- **Booking:** compare anche `202` senza titolo o anteprima utile. Non equivale a una pagina completa.

## Tempi

Le coppie selezionate hanno risposte 2xx, stesso status, URL finale e tipo di contenuto, tempi presenti e nessun indicatore di challenge su entrambi i lati. Il corpo può comunque differire. La differenza mediana è calcolata sulle coppie, non sottraendo le due mediane.

| Esecuzione | Coppie | Mediana upstream | Mediana fork | Mediana fork − upstream |
|---|---:|---:|---:|---:|
| Baseline AB | 57 | 306 ms | 257 ms | −32 ms |
| Baseline BA | 56 | 279 ms | 246 ms | −31 ms |
| User-Agent uguale | 57 | 292 ms | 275 ms | −29 ms |
| Redirect | 78 | 334 ms | 263 ms | −75 ms |
| Controllo nativo | 59 | 292 ms | 274 ms | −7 ms |

Queste latenze descrivono il campione. DNS, cache, pooling, protocollo, compressione, corpo e ordine delle richieste differiscono. Il limite di frequenza domina la durata totale: non è un test di throughput o una garanzia di velocità.

## Trasporto osservato

Due richieste aggiuntive all'endpoint pubblico `tls.peet.ws/api/all`, con lo stesso User-Agent Chrome 155, hanno rilevato:

| Campo | Upstream | Fork |
|---|---|---|
| Protocollo negoziato | HTTP/1.1 | HTTP/2 |
| JA3 hash | `99c071c5a5e14cc2527c9e8e0dde4a50` | `2e6d826272bac9f491a95a79fcc4888b` |
| JA4 | `t13d2511_b78ed14e2fd0_f50d94e863eb` | `t13d1517h2_8daaf6152771_cb7bf5808d99` |

Questo conferma un trasporto diverso a parità di User-Agent; non isola il contributo del TLS rispetto a HTTP/2 o agli header. JA3 può cambiare con l'ordine casuale delle estensioni TLS. I [campi conservati](fingerprints.json) includono il fingerprint HTTP/2 del fork; IP del client e risposta completa dell'endpoint non sono stati salvati.

## Validazione del codice

La [verifica completa](validation.md) riporta comandi e limiti. Sono passati la suite Go con Go 1.26.0 (8 pacchetti con test), `go vet`, il race detector mirato (19 test principali, 46 risultati con i sottocasi), le build Linux AMD64 e macOS ARM64, i 10 controlli locali dei comandi del benchmark e i 26 test Python del harness e del report.

Nei test CLI locali il trasporto browser passa 16 casi e rifiuta i 3 casi raw/unsafe non supportati; il controllo nativo passa tutti i 19. La build Linux è stata compilata, non eseguita. Non abbiamo testato ogni preset, ogni variante di proxy o carichi prolungati; il bridge non supporta HTTP/3. La suite funzionale pubblica opzionale di 24 casi non è stata eseguita; i test pubblici di questa sessione sono quelli documentati qui.

## Metodo, riproduzione e correzioni

Upstream è httpx **v1.12.0**, commit `4b6a9a9d476f94a4f3a630f37051f5671ecfb1f8`. Il fork usa **HTTPcloak v1.7.3**, profilo `chrome-latest`, che in questa build emette uno User-Agent Chrome 155. Entrambi i binari del benchmark sono stati compilati con Go 1.27.2 sulla stessa macchina macOS ARM64. Versioni, hash, comandi, orari e ambiente sono conservati nei `metadata.json` delle esecuzioni.

Parametri comuni: **3 probe iniziali/secondo**, 3 thread, timeout 12 secondi, zero retry configurati, nessun fallback di schema, lettura massima 2 MiB e anteprima 300 byte. Sono richieste GET anonime, senza proxy, credenziali o cookie personali ereditati; HOME, XDG e configurazione sono isolati. I corpi oltre il limite possono essere troncati e gli hash diversi possono dipendere dal contenuto dinamico.

Il campione è scelto manualmente e non rappresenta tutto il web. Una sola rete, un solo momento e due ordini baseline non consentono stime generali di affidabilità. User-Agent uguale non significa header, DNS, compressione, pooling o protocollo uguali. Gli status e l'assenza di indicatori di challenge non certificano accesso utile o equivalenza dei contenuti.

Per preparare i binari dalla root del progetto, scegliere una directory temporanea libera per upstream:

```sh
make build
git clone --branch v1.12.0 --depth 1 \
  https://github.com/projectdiscovery/httpx.git /tmp/httpx-v1.12.0
go -C /tmp/httpx-v1.12.0 build -trimpath \
  -o "$PWD/bin/httpx-upstream-v1.12.0" ./cmd/httpx
```

Per verificare localmente i comandi, senza interrogare siti pubblici:

```sh
python3 scripts/check_benchmark_cli.py \
  --upstream bin/httpx-upstream-v1.12.0 --fork bin/undetected-httpx
python3 -m unittest discover -s scripts -p 'test_*httpx*.py'
```

Per una nuova acquisizione pubblica, usando un nome di output nuovo:

```sh
python3 scripts/compare_httpx.py run \
  --targets docs/benchmarks/2026-10-16/targets.csv \
  --upstream bin/httpx-upstream-v1.12.0 --fork bin/undetected-httpx \
  --mode defaults --round 1 --output docs/benchmarks/new-baseline
```

`--reverse` inverte l'ordine. Le altre modalità sono `matched`, `redirects` e `native`; per `matched` e `native` specificare `--user-agent` uguale su entrambi, come registrato nei metadata. Per rigenerare il report dai dati salvati, senza rete:

```sh
python3 scripts/render_httpx_comparison.py \
  --root docs/benchmarks/2026-10-16 \
  --runs baseline-ab-verified baseline-ba-verified matched-verified \
    redirects-verified native-control-verified
```

**Correzione del harness.** Quattro acquisizioni preliminari usavano `-bp 300`. Il parser si fermava sul valore posizionale `300`, ignorando i flag successivi, inclusi frequenza, User-Agent e redirect. Abbiamo escluso queste acquisizioni dal repository e dai risultati, corretto in `-bp=300`, verificato i parametri effettivi su localhost e ripetuto le prove. Quelle acquisizioni iniziali hanno generato traffico aggiuntivo e non sono incluse nelle 960 osservazioni valide.

L'analisi corrente è la **revisione 3**: riconosce anche “Client Challenge”, “Verifying your connection”, “Your request has been blocked” e “Prove your humanity”, ed esclude le challenge note dalle latenze comparabili. I summary distinguono l'hash dello script di acquisizione da quello dell'analisi. Il renderer rifiuta esplicitamente le acquisizioni invalidate.

Prima della pubblicazione abbiamo rimosso dalle copie dei JSONL l'IP del client e i token di sessione restituiti dai siti. Il [manifest delle redazioni](redaction-manifest.json) registra i campi interessati e gli hash dei file originali e pubblicati. Status, titoli, tempi e risultati del confronto restano invariati; i metadata verificano gli hash delle copie pubblicate. Gli script di acquisizione salvano le risposte ricevute: prima di condividere nuove acquisizioni, controllare anche questi campi.
