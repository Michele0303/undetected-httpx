# Verifiche della v2, 16 ottobre 2026

Ho eseguito i test sulla working tree v2 con Go 1.26.0, macOS ARM64. La suite Go, il race detector mirato, `go vet` e le due build hanno completato senza errori. Nei test CLI locali il trasporto browser passa 16 casi su 19; rifiuta i tre casi `-unsafe`, come previsto. Con `-native-http` passano tutti i 19 casi.

Ho verificato la migrazione v2 a partire dal commit base `3c079d2c537e93430ba7a4263f04da3ec3c8b87b`. Le build includono le modifiche della v2 sul branch `mf/v2-httpcloak`; il solo commit base contiene ancora la versione Python. Gli hash sotto identificano i binari usati.

## Risultati

| Verifica | Risultato | Dettaglio |
|---|---|---|
| `GOTOOLCHAIN=go1.26.0 go test -count=1 -timeout 2m ./...` | PASS | 8 pacchetti con test; 17 senza test. Nessun uso della cache dei risultati. |
| `GOTOOLCHAIN=go1.26.0 go vet ./...` | PASS | Nessuna diagnostica. |
| Race detector su `common/httpx` e `runner` | PASS | 19 test principali, 46 risultati includendo i sottocasi; zero skip e zero errori. |
| Integration CLI, default browser | 16 PASS, 3 rifiuti attesi | Tutti i casi su server `httptest` locali. Il programma termina con exit code 1 perché la suite upstream considera i tre rifiuti come fallimenti. |
| Integration CLI, `-native-http` | 19 PASS | Exit code 0. |
| Build Linux AMD64, `CGO_ENABLED=0` | PASS | ELF x86-64 statico; compilazione soltanto, senza esecuzione su Linux. |
| Build macOS ARM64, `CGO_ENABLED=0` | PASS | Mach-O ARM64; usata per i test CLI locali. |

Comando del race detector:

```sh
GOTOOLCHAIN=go1.26.0 go test -race -json ./common/httpx ./runner \
  -run 'Test(Cloak|Browser|NativeHTTP)' -count=1 -timeout 2m
```

Comandi delle build:

```sh
GOTOOLCHAIN=go1.26.0 CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
  go build -o /tmp/undetected-httpx-validation-linux-amd64 ./cmd/undetected-httpx
GOTOOLCHAIN=go1.26.0 CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 \
  go build -o /tmp/undetected-httpx-validation-darwin-arm64 ./cmd/undetected-httpx
```

SHA-256 dei binari di questa verifica:

| Binario | SHA-256 |
|---|---|
| Linux AMD64 | `32271f24f54945ca75b99b5d0b43580fbc83830c7be2a07060f9d8b7140fe478` |
| macOS ARM64 | `10fa0b70825bc4dfbbd0ec9cd760395780f2c91f7f802a66c093710b0a37bf2e` |

## Test CLI locali

Ho compilato `./cmd/integration-test` in `/tmp/undetected-httpx-validation-integration`. Il programma cerca `./httpx`: ho creato due wrapper temporanei che invocano il binario macOS appena compilato, uno con `-duc` e uno con `-duc -native-http`. Ho eseguito il programma con `PROTO=http` nelle rispettive directory. Questa selezione copre i 19 casi HTTP su server locali ed esclude i due casi SDK che contattano `scanme.sh`.

La suite verifica GET HTTP/HTTPS, header personalizzati, output e filtri, redirect, gzip malformato, POST con corpo, path e regressioni ereditate da upstream. I tre casi che il browser rifiuta sono:

- `Raw HTTP GET Request`
- `Raw request with non standard rfc path via stdin`
- `Raw request with non standard rfc path via cli flag`

Ho confermato il motivo con una chiamata CLI separata, che termina prima della richiesta:

```text
[FTL] browser transport does not support -unsafe; use -native-http for these features
```

La prima invocazione del wrapper nativo usava per errore il flag inesistente `-http-transport native` e ha prodotto 19 errori di parsing. Ho corretto il wrapper in `-native-http` e rieseguito la suite: 19/19 passati. Gli errori della prima invocazione non indicano un difetto del prodotto.

## Copertura e limiti

I test dedicati al trasporto coprono HTTP/1.1 e HTTP/2, negoziazione e HTTP/2 forzato, header ripetuti, Host, risposte senza corpo, decompressione gzip/deflate/Brotli/Zstandard, limite di lettura, cookie e redirect, replay del corpo POST, cancellazione dello stream, deadline e proxy CONNECT locale. I test del runner verificano il probe locale e il rifiuto delle opzioni incompatibili.

L'adattatore corrente non usa HTTP/3. Il test di compatibilità verifica che `-pr http3` venga rifiutato. Per SNI personalizzato, TLS grab/probe, resolver e politiche IP occorre `-native-http`; i test verificano il rifiuto nel trasporto browser. I metadati TLS disponibili nel bridge HTTP/2 non equivalgono alla compatibilità completa dei flag TLS upstream.

Il test proxy esistente usa un proxy HTTP locale con CONNECT verso un'origine HTTP. Non copre proxy HTTPS, SOCKS5/SOCKS5H, autenticazione proxy o catene proxy. Non ho verificato questi percorsi in questa sessione. Non ho eseguito una prova di carico prolungata né testato ogni preset browser.

Ho letto i 24 casi di `cmd/functional-test/testcases.txt`, diretti a `scanme.sh` e `example.com`, ma non li ho eseguiti: il confronto pubblico di questa sessione misura già le richieste remote e conserva i relativi risultati. I conteggi di questo documento descrivono la validazione del codice e la compatibilità CLI locale; per le differenze fra siti occorre consultare il report del benchmark.

## Verifica dei comandi del benchmark

Ho trovato un errore nell'invocazione iniziale del benchmark: `-bp 300`. Il flag `-bp` accetta un valore opzionale e il parser interpreta `300` come argomento posizionale; a quel punto smette di leggere i flag successivi. Di conseguenza ignorava `-hash`, rate limit, timeout, UA, redirect e l'eventuale selezione del trasporto nativo. I run con questa forma non sono validi per il confronto dichiarato e vanno esclusi dai risultati.

La forma corretta è `-bp=300`. Ho riprodotto il problema su un server locale che restituisce `302 /start → 200 /final`: con il comando iniziale entrambi i binari restituivano 302 senza hash. Cambiando quel solo argomento, entrambi restituivano 200, `final_url`, catena `[302,200]` e hash del corpo corretto. `-location` e la configurazione vuota non impediscono i redirect.

Ho aggiunto [scripts/check_benchmark_cli.py](../../../scripts/check_benchmark_cli.py), che usa la funzione `command_for` del harness per evitare una seconda copia dei comandi. Avvia un server su `127.0.0.1` e verifica i binari reali:

| Modalità | Verifica locale | Risultato |
|---|---|---|
| `defaults` | 302 senza follow; hash corretto; UA HTTPX deterministico e UA Chrome del fork | PASS su entrambi |
| `matched` | Stesso header `User-Agent: httpx-cli-preflight/1.0`; 302 e hash corretto | PASS su entrambi |
| `redirects` | Due richieste `/start`, `/final`; 200, catena `[302,200]`, URL finale e hash corretto | PASS su entrambi |
| `native` | Comando del harness con `-native-http` per il fork e stessa UA esplicita; 302 e hash corretto | PASS su entrambi |
| Rate limit | 12 URL locali a 3 richieste/secondo | PASS: intervallo prima/ultima richiesta 3,001 s su entrambi |

I 10 controlli hanno completato in circa 8 secondi. La prova del rate limit ha osservato quattro gruppi di tre richieste a circa un secondo di distanza. Il limite riguarda i probe iniziali: i redirect di un probe aggiungono richieste.

Per ripetere il controllo, dalla root del progetto:

```sh
python3 scripts/check_benchmark_cli.py \
  --upstream bin/httpx-upstream-v1.12.0 \
  --fork bin/undetected-httpx
```

Il controllo stampa JSON e termina con errore se una delle verifiche fallisce. Ho verificato questi binari del benchmark, distinti dalle build temporanee della tabella precedente:

| Binario del benchmark | SHA-256 |
|---|---|
| Upstream v1.12.0 | `5861aa7ee38cea98e0d6561a09e062f02435cfe8599c0a79093ee325bda3579b` |
| Fork v2 | `ed6b74bd7b77674269e3257091a173e6997d688c6f14c87c47f96b5808944649` |

Non ho modificato il codice del trasporto durante queste verifiche.

## Analisi e presentazione dei risultati

I 26 test Python del harness e del renderer passano con:

```sh
python3 -m unittest discover -s scripts -p 'test_*httpx*.py'
```

Verificano associazione input/output, risultati mancanti o duplicati, errori di processo, durate, redirect, riconoscimento delle pagine di verifica tramite header e titolo, esclusione delle challenge note dalle latenze selezionate e rifiuto delle acquisizioni invalidate. La revisione 3 dell'analisi aggiunge il titolo Reddit “Prove your humanity”; tutte le cinque acquisizioni valide sono state rianalizzate senza modificare i JSONL originali.

Gli hash dei JSONL pubblicati, degli stderr e degli input corrispondono ai metadata delle cinque acquisizioni. Prima del push abbiamo rimosso IP del client e token di sessione dalle copie pubblicate e verificato che i risultati del confronto restassero invariati; il [manifest](redaction-manifest.json) conserva gli hash precedenti e successivi. `git diff --check` non riporta errori.

## Controllo prima del commit, 17 ottobre 2026

Dopo la pulizia del repository sono passati `make test`, i 26 test Python e `go vet ./...`. Tutti i file Go rispettano `gofmt`. GoReleaser 2.18.3 ha validato la configurazione; un archivio di prova ha conservato i percorsi dei 114 file previsti ed escluso le directory temporanee dei benchmark e le nuove catture non pubblicate. Questo controllo non ha ricompilato l'immagine Docker né pubblicato una release.
