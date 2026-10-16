#!/usr/bin/env python3
"""Render completed httpx benchmark captures as a standalone Italian HTML report."""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo


ARMS = ("upstream", "fork")
STATE_NAMES = {"http_response": "HTTP", "request_failure": "errore richiesta",
               "missing": "output assente", "ambiguous": "output duplicato",
               "invalid_result": "output non valido"}
MODE_NAMES = {"defaults": "Profilo predefinito", "matched": "User-Agent uguale",
              "redirects": "Redirect", "native": "Controllo native"}


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def integer(value):
    return int(value) if value not in (None, "") else None


def decimal(value):
    return float(value) if value not in (None, "") else None


def flag(value):
    return str(value).lower() == "true"


def read_targets(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows or any(not row.get("id") or not row.get("url") for row in rows):
        raise ValueError(f"Invalid or empty target dataset: {path}")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError(f"Duplicate target IDs: {path}")
    return rows


def load_run(path):
    if (path / "INVALIDATED.md").exists():
        raise ValueError(f"Invalidated capture: {path}")
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    if summary.get("validity", {}).get("controlled_comparison_valid") is False:
        raise ValueError(f"Invalid controlled comparison: {path}")
    for arm in ARMS:
        command = metadata.get("arms", {}).get(arm, {}).get("command", [])
        for index, argument in enumerate(command[:-1]):
            if argument in ("-bp", "-body-preview") and not command[index + 1].startswith("-"):
                raise ValueError(f"Invalid separated -bp value stops CLI flag parsing: {path}/{arm}")
    if not metadata.get("finished_at"):
        raise ValueError(f"Capture has not finished: {path}")
    rows = {arm: {} for arm in ARMS}
    with (path / "normalized.csv").open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            arm, target_id = row.get("arm"), row.get("id")
            if arm not in rows or not target_id or target_id in rows[arm]:
                raise ValueError(f"Unknown arm or duplicate/missing target ID: {path}")
            row["status"] = integer(row.get("status"))
            row["content_length"] = integer(row.get("content_length"))
            row["time_seconds"] = decimal(row.get("time_seconds"))
            for name in ("challenge_heuristic", "process_failed", "process_timed_out"):
                row[name] = flag(row.get(name))
            for name in ("chain_status_codes", "challenge_evidence"):
                row[name] = json.loads(row.get(name) or "[]")
            rows[arm][target_id] = row
    if set(rows["upstream"]) != set(rows["fork"]):
        raise ValueError(f"Arms have different normalized target sets: {path}")
    for arm in ARMS:
        entries = list(rows[arm].values())
        if len(entries) != summary["target_count"]:
            raise ValueError(f"Target count disagrees with summary: {path}/{arm}")
        expected = summary["arms"][arm]
        if dict(Counter(row["state"] for row in entries)) != expected["states"]:
            raise ValueError(f"State totals disagree with summary: {path}/{arm}")
        if sum(is_http(row) for row in entries) != expected["http_responses"]:
            raise ValueError(f"HTTP totals disagree with summary: {path}/{arm}")
        if sum(is_2xx(row) for row in entries) != expected["http_2xx"]:
            raise ValueError(f"2xx totals disagree with summary: {path}/{arm}")
    return {"path": path, "name": path.name, "summary": summary,
            "metadata": metadata, "rows": rows}


def is_http(row):
    return row.get("state") == "http_response"


def is_2xx(row):
    return is_http(row) and isinstance(row.get("status"), int) and 200 <= row["status"] < 300


def state_key(row):
    return (row.get("state"), row.get("status") if is_http(row) else None)


def state_label(row):
    return str(row["status"]) if is_http(row) else STATE_NAMES.get(row.get("state"), row.get("state", ""))


def pair(run, target_id):
    if target_id not in run["rows"]["upstream"]:
        return None
    return tuple(run["rows"][arm][target_id] for arm in ARMS)


def repeated_deltas(runs, targets):
    """Find state/status differences reproduced in both baseline orders."""
    baseline = [run for run in runs if run["summary"]["mode"] == "defaults"]
    ab = next((run for run in baseline if run["metadata"].get("order") == list(ARMS)), None)
    ba = next((run for run in baseline if run["metadata"].get("order") == list(reversed(ARMS))), None)
    if not ab or not ba:
        return None, [], []
    repeated, changed = [], []
    for target in targets:
        first, second = pair(ab, target["id"]), pair(ba, target["id"])
        if first is None or second is None:
            continue
        states1, states2 = tuple(map(state_key, first)), tuple(map(state_key, second))
        if states1 != states2:
            changed.append(target["id"])
        elif states1[0] != states1[1]:
            repeated.append(target["id"])
    return (ab, ba), repeated, changed


def relative_link(output, path):
    import os
    return quote(os.path.relpath(path, output.parent), safe="/")


def link_file(output, path, label):
    return f'<a href="{esc(relative_link(output, path))}">{esc(label)}</a>'


def target_link(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username:
        return esc(url)
    return f'<a href="{esc(url)}" target="_blank" rel="noreferrer noopener">{esc(url)}</a>'


def milliseconds(value, signed=False):
    if value is None:
        return "—"
    return f'{value * 1000:{"+" if signed else ""}.0f} ms'


def seconds(value):
    return "—" if value is None else f"{value:.1f} s"


def badge(row, arm):
    kind = "ok" if is_2xx(row) else "redirect" if is_http(row) and 300 <= row["status"] < 400 else "error" if not is_http(row) else "other"
    marker = " · challenge*" if row.get("challenge_heuristic") else ""
    return f'<span class="badge {kind}"><b>{"U" if arm == "upstream" else "F"}</b> {esc(state_label(row) + marker)}</span>'


def observation_detail(row, arm):
    fields = [("Titolo", row.get("title") or "(vuoto)"), ("URL finale", row.get("final_url") or "—"),
              ("Location", row.get("location") or "—"), ("Tipo", row.get("content_type") or "—"),
              ("Lunghezza riportata", row.get("content_length")),
              ("Tempo richiesta", milliseconds(row.get("time_seconds"))),
              ("SHA-256 corpo", row.get("body_sha256") or "—")]
    if row.get("chain_status_codes"):
        fields.append(("Catena status", " → ".join(map(str, row["chain_status_codes"]))))
    if row.get("challenge_evidence"):
        fields.append(("Evidenza challenge*", "; ".join(row["challenge_evidence"])))
    if row.get("error"):
        fields.append(("Errore", row["error"]))
    if row.get("process_failed"):
        fields.append(("Processo", "exit=" + str(row.get("process_exit_code")) + "; timeout=" + str(row.get("process_timed_out"))))
    return '<div class="observation"><strong>' + ("Upstream" if arm == "upstream" else "Fork") + '</strong><dl>' + "".join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k, v in fields) + '</dl></div>'


def pair_cell(run, target_id):
    observed = pair(run, target_id)
    if observed is None:
        return '<td class="outside">Fuori campione</td>'
    a, b = observed
    labels = []
    if state_key(a) != state_key(b):
        labels.append("esito diverso")
    if a.get("title") != b.get("title"):
        labels.append("titolo diverso")
    if any(not is_http(row) or row.get("process_failed") for row in observed):
        labels.append("errore / diagnostica")
    badges = badge(a, "upstream") + badge(b, "fork")
    detail = observation_detail(a, "upstream") + observation_detail(b, "fork")
    return '<td><div class="badges">' + badges + '</div><details><summary>' + esc(", ".join(labels) or "Dettagli") + '</summary>' + detail + '</details></td>'


def status_count(run, arm, status):
    return sum(is_http(row) and row["status"] == status for row in run["rows"][arm].values())


def findings_section(runs):
    paragraphs, native_rows = [], []
    for run in runs:
        mode, s = run["summary"]["mode"], run["summary"]
        if mode not in ("matched", "redirects", "native"):
            continue
        u, f = s["arms"]["upstream"], s["arms"]["fork"]
        start = '<b>' + esc(run["name"]) + '</b>: '
        if mode == "matched":
            paragraphs.append(start + f'con lo stesso User-Agent, upstream riceve {u["http_2xx"]} risposte 2xx e il fork {f["http_2xx"]}. I 403 sono {status_count(run, "upstream", 403)} e {status_count(run, "fork", 403)}. Header e altri comportamenti del trasporto possono ancora differire.')
        elif mode == "redirects":
            paired = [pair(run, target_id) for target_id in run["rows"]["upstream"]]
            gains = sum(is_http(a) and not is_2xx(a) and is_2xx(b) for a, b in paired)
            reverse = sum(is_2xx(a) and is_http(b) and not is_2xx(b) for a, b in paired)
            paragraphs.append(start + f'seguendo i redirect, upstream riceve {u["http_2xx"]} risposte 2xx e il fork {f["http_2xx"]}. Su {gains} URL il fork passa da un codice non-2xx a un 2xx; il passaggio inverso compare su {reverse} URL. I 403 sono {status_count(run, "upstream", 403)} / {status_count(run, "fork", 403)}; i 406 sono {status_count(run, "upstream", 406)} / {status_count(run, "fork", 406)}.')
        else:
            pairs = [pair(run, target_id) for target_id in run["rows"]["upstream"]]
            same = sum(state_key(a) == state_key(b) for a, b in pairs)
            paragraphs.append(start + f'con entrambi i trasporti native, {same} URL su {len(pairs)} hanno lo stesso stato/status. Le differenze residue mostrano che tempo, percorso di rete o altri dettagli possono incidere anche senza httpcloak; non consentono di attribuire ogni differenza al trasporto browser.')
            for a, b in pairs:
                if state_key(a) != state_key(b):
                    native_rows.append('<tr><td>' + target_link(a["url"]) + '</td><td>' + esc(state_label(a)) + '</td><td>' + esc(state_label(b)) + '</td><td>' + esc(a.get("title") or "(vuoto)") + '</td><td>' + esc(b.get("title") or "(vuoto)") + '</td></tr>')
    challenge_examples = {}
    for run in runs:
        for arm in ARMS:
            for row in run["rows"][arm].values():
                if is_http(row) and row["status"] == 200 and row.get("challenge_heuristic"):
                    transport = "native" if run["summary"]["mode"] == "native" else "browser"
                    label = ("Fork " + transport) if arm == "fork" else "Upstream"
                    key = (label, row["url"], row.get("title", ""))
                    challenge_examples.setdefault(key, []).append(run["name"])
    warning = ''
    if challenge_examples:
        examples = ''.join('<li><b>' + esc(label) + '</b>: ' + target_link(url) + ' restituisce <b>200</b> con titolo <q>' + esc(title or "(vuoto)") + '</q>. <small>Esecuzioni: ' + esc(', '.join(challenge_examples[(label, url, title)])) + '</small></li>' for label, url, title in sorted(challenge_examples))
        warning = '<aside class="finding-warning"><h3>Un HTTP 200 può contenere una challenge</h3><p>Questi esempi compaiono nelle capture. Il codice HTTP non conferma l’accesso al contenuto richiesto; un titolo generico nell’altro strumento non basta a confermarlo.</p><ul>' + examples + '</ul></aside>'
    native_table = ('<h3>Differenze nel controllo native</h3><div class="table-scroll"><table><thead><tr><th>URL</th><th>Upstream</th><th>Fork native</th><th>Titolo upstream</th><th>Titolo fork</th></tr></thead><tbody>' + ''.join(native_rows) + '</tbody></table></div>') if native_rows else ''
    return '<section id="lettura"><h2>Cosa mostrano questi test</h2><p>I conteggi 2xx descrivono i codici HTTP ricevuti. <b>Non misurano quanti siti offrono contenuto utilizzabile.</b></p>' + ''.join('<p>' + item + '</p>' for item in paragraphs) + warning + native_table + '</section>'


def summary_section(runs):
    body = []
    latency = []
    for run in runs:
        s, meta = run["summary"], run["metadata"]
        u, f = (s["arms"][arm] for arm in ARMS)
        partial = '<small>Campione selezionato: non confrontare i totali con il campione completo.</small>' if run.get("partial") else ""
        name = f'<strong>{esc(run["name"])}</strong><small>{esc(MODE_NAMES.get(s["mode"], s["mode"]))} · {" → ".join("U" if x == "upstream" else "F" for x in meta.get("order", []))}</small>{partial}'
        counts = [f'{u[key]} / {f[key]}' for key in ("http_responses", "http_2xx")]
        counts += [f'{status_count(run, "upstream", status)} / {status_count(run, "fork", status)}' for status in (403, 406)]
        counts.append(f'{u["challenge_heuristic"]} / {f["challenge_heuristic"]}')
        errors = [sum(count for state, count in arm["states"].items() if state != "http_response") for arm in (u, f)]
        body.append('<tr><td>' + name + '</td><td>' + str(s["target_count"]) + '</td>' + ''.join('<td>' + value + '</td>' for value in counts) + f'<td>{errors[0]} / {errors[1]}</td><td>{s["transitions"]["different_status"]}</td></tr>')
        l = s["latency"]
        wall = [meta.get("arms", {}).get(arm, {}).get("duration_seconds") for arm in ARMS]
        latency.append('<tr><td>' + esc(run["name"]) + '</td><td>' + str(l["pair_count"]) + '</td><td>' + milliseconds(l["upstream_median_seconds"]) + '</td><td>' + milliseconds(l["fork_median_seconds"]) + '</td><td>' + milliseconds(l["paired_delta_fork_minus_upstream_median_seconds"], True) + '</td><td>' + seconds(wall[0]) + ' / ' + seconds(wall[1]) + '</td></tr>')
    return (
        '<section id="risultati"><h2>Risultati per esecuzione</h2><p>Ogni coppia riporta <b>upstream / fork</b>. Gli HTTP 4xx e 5xx contano come risposte HTTP. Un errore di richiesta e un output assente hanno stati distinti nei dettagli.</p><div class="table-scroll"><table><thead><tr><th>Esecuzione</th><th>URL</th><th>Risposte HTTP</th><th>HTTP 2xx</th><th>403</th><th>406</th><th>Challenge/blocco*</th><th>Esiti senza HTTP</th><th>Status HTTP diversi</th></tr></thead><tbody>'
        + ''.join(body)
        + '</tbody></table></div><h3>Tempi sulle coppie selezionate</h3><p>Solo risposte 2xx con stesso status, URL finale e tipo di contenuto. La selezione esclude le pagine che l’euristica identifica come challenge o blocco. Il corpo può differire. La differenza mediana usa le coppie; non equivale alla differenza fra le due mediane. I tempi totali includono attese e limiti di frequenza.</p><div class="table-scroll"><table><thead><tr><th>Esecuzione</th><th>Coppie</th><th>Mediana upstream</th><th>Mediana fork</th><th>Mediana (fork − upstream)</th><th>Tempo totale U / F</th></tr></thead><tbody>'
        + ''.join(latency) + '</tbody></table></div></section>'
    )


def repeated_section(baselines, repeated, changed, targets):
    if baselines is None:
        return '<section id="ripetizione"><h2>Ripetizione AB / BA</h2><p>Servono entrambe le esecuzioni del profilo predefinito, con ordine invertito, per calcolare le differenze ripetute.</p></section>'
    ab, ba = baselines
    target_map = {t["id"]: t for t in targets}
    rows = []
    for target_id in repeated:
        a1, b1 = pair(ab, target_id)
        a2, b2 = pair(ba, target_id)
        rows.append('<tr><td>' + target_link(target_map[target_id]["url"]) + '</td>' + ''.join('<td>' + esc(state_label(row)) + '</td>' for row in (a1, b1, a2, b2)) + '</tr>')
    table = '<div class="table-scroll"><table><thead><tr><th>URL</th><th>U, AB</th><th>F, AB</th><th>U, BA</th><th>F, BA</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>' if rows else '<p>Nessuna differenza di stato/status si ripete nei due ordini.</p>'
    return f'<section id="ripetizione"><h2>Differenze ripetute nei due ordini</h2><p><b>{len(repeated)} URL</b> mostrano la stessa differenza di stato/status in AB e BA. Su <b>{len(changed)} URL</b> almeno uno dei due strumenti cambia stato/status fra le esecuzioni. Due osservazioni descrivono la ripetibilità di questo test; non dimostrano una proprietà generale del sito.</p>' + table + '</section>'


def target_section(runs, targets, repeated):
    body = []
    repeated = set(repeated)
    for target in targets:
        observed = [p for run in runs if (p := pair(run, target["id"])) is not None]
        changed = any(state_key(a) != state_key(b) for a, b in observed)
        titles = any(a.get("title") != b.get("title") for a, b in observed)
        errors = any(not is_http(row) or row.get("process_failed") for p in observed for row in p)
        search = " ".join([target["url"], target.get("group", "")] + [str(row.get(key) or "") for p in observed for row in p for key in ("title", "error", "status")]).lower()
        body.append(f'<tr data-search="{esc(search)}" data-changed="{int(changed)}" data-titles="{int(titles)}" data-errors="{int(errors)}" data-repeated="{int(target["id"] in repeated)}"><th scope="row">' + target_link(target["url"]) + '<small>' + esc(target.get("group", "")) + '</small></th>' + ''.join(pair_cell(run, target["id"]) for run in runs) + '</tr>')
    headings = ''.join('<th>' + esc(run["name"]) + ('<small>Campione selezionato</small>' if run.get("partial") else '') + '</th>' for run in runs)
    return '<section id="url"><h2>Confronto URL per URL</h2><p><b>U</b> = ProjectDiscovery httpx. <b>F</b> = undetected-httpx. Apri i dettagli per titoli, errori, destinazioni, hash e tempi. “Fuori campione” indica un URL non incluso in quella esecuzione.</p><div class="filters"><label>Cerca URL, gruppo, titolo o errore<input id="query" type="search" placeholder="Es. cloudflare, 403, timeout" autocomplete="off"></label><label>Mostra<select id="filter"><option value="all">Tutti gli URL</option><option value="changed">Stato o status diverso</option><option value="repeated">Differenza ripetuta AB / BA</option><option value="titles">Titolo diverso</option><option value="errors">Errori o output assenti</option></select></label><output id="visible" aria-live="polite">' + str(len(targets)) + ' URL</output></div><div class="table-scroll host-table"><table id="targets"><thead><tr><th>URL / gruppo</th>' + headings + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div></section>'


def diagnostics_section(runs, output):
    parts = []
    for run in runs:
        rows = []
        for arm in ARMS:
            process = run["metadata"].get("arms", {}).get(arm, {})
            diagnostics = run["summary"].get("diagnostics", {}).get(arm, {})
            rows.append('<p><b>' + esc(arm) + '</b>: exit ' + esc(process.get("exit_code")) + '; timeout ' + esc(process.get("timed_out")) + '; righe JSON non valide ' + str(len(diagnostics.get("invalid_json_lines", []))) + '; record senza corrispondenza ' + str(len(diagnostics.get("unmatched_records", []))) + '. ' + link_file(output, run["path"] / (arm + ".stderr.log"), "Log stderr") + '</p>')
            failures = [row for row in run["rows"][arm].values() if not is_http(row)]
            if failures:
                rows.append('<ul>' + ''.join('<li><code>' + esc(row["url"]) + '</code>: ' + esc(state_label(row)) + (': ' + esc(row.get("error")) if row.get("error") else '') + '</li>' for row in failures) + '</ul>')
        parts.append('<details><summary>' + esc(run["name"]) + '</summary>' + ''.join(rows) + '</details>')
    return '<section id="diagnostica"><h2>Diagnostica</h2>' + ''.join(parts) + '</section>'


def method_section(runs, output, dataset):
    links = []
    for run in runs:
        names = ("report.md", "summary.json", "normalized.csv", "metadata.json", "upstream.jsonl", "fork.jsonl")
        links.append('<li><b>' + esc(run["name"]) + '</b>: ' + ' · '.join(link_file(output, run["path"] / name, name) for name in names) + '</li>')
    settings = []
    for run in runs:
        m = run["metadata"]
        settings.append('<tr><td>' + esc(run["name"]) + '</td><td>' + esc(m.get("rate_limit_per_second")) + '</td><td>' + esc(m.get("threads")) + '</td><td>' + esc(m.get("timeout_seconds")) + ' s</td><td>' + esc(m.get("retries")) + '</td><td>' + esc(m.get("body_read_limit_bytes")) + '</td></tr>')
    limits = [
        'AB esegue prima upstream, BA prima il fork. I due strumenti interrogano i siti in momenti diversi; CDN, cache, carico e ordine possono modificare l’esito.',
        'Il profilo predefinito usa uno User-Agent upstream fisso e il profilo browser del fork. Il controllo con User-Agent uguale conserva differenze di DNS, header, compressione, versione HTTP e riuso delle connessioni. Non isola il solo fingerprint TLS.',
        'Un passaggio da 403 a 200 non prova un bypass né l’equivalenza del contenuto. <b>Challenge*</b> indica un’euristica basata su header e titoli; può includere falsi positivi e perdere challenge.',
        'Il limite di frequenza riguarda i probe iniziali. Redirect e richieste interne del trasporto possono aggiungere traffico. Con <code>-maxr 3</code>, httpx conta anche la richiesta iniziale e segue al massimo due redirect.',
        'Il limite di lettura può troncare i corpi e influire su hash, lunghezze e tempi. Un hash diverso può dipendere da timestamp, cookie, localizzazione o altro contenuto dinamico. La lunghezza riportata può derivare dall’header Content-Length.',
        'Le latenze descrivono queste richieste e non misurano la capacità massima.',
        'Il processo riceve un ambiente consentito esplicito, HOME/XDG isolati e una configurazione vuota. Il test non eredita proxy, cookie, credenziali o configurazioni personali.',
    ]
    if any(run.get("partial") for run in runs):
        limits.append('Alcune esecuzioni coprono un sottoinsieme selezionato, indicato nelle tabelle. I loro totali non vanno confrontati con quelli dei campioni completi.')
    supporting = [link_file(output, dataset.parent / name, label)
                  for name, label in (("README.md", "Conclusioni e metodo"),
                                      ("validation.md", "Verifica dei test"),
                                      ("fingerprints.json", "Fingerprint osservati"))
                  if (dataset.parent / name).is_file()]
    documents = '<p>' + ' · '.join(supporting) + '</p>' if supporting else ''
    return (
        '<section id="metodo"><h2>Metodo e limiti</h2><p>Abbiamo confrontato una selezione di URL pubblici e sottodomini. Ogni esecuzione conserva input, comandi, hash dei binari, versioni, output JSONL, stderr e tempi. Il confronto associa le risposte all’input originale, anche in presenza di redirect. '
        + link_file(output, dataset, "Dataset completo")
        + '.</p><div class="table-scroll"><table><thead><tr><th>Esecuzione</th><th>Probe iniziali / s</th><th>Thread</th><th>Timeout</th><th>Retry configurati</th><th>Limite lettura, byte</th></tr></thead><tbody>'
        + ''.join(settings) + '</tbody></table></div><ul>'
        + ''.join('<li>' + item + '</li>' for item in limits)
        + '</ul><h3>Documentazione e dati</h3>' + documents + '<ul>' + ''.join(links) + '</ul></section>'
    )


STYLE = """
:root{color-scheme:light;--ink:#182720;--muted:#5b6b63;--line:#d4ded7;--paper:#f4f7f3;--accent:#195f44}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1500px;margin:auto;padding:48px 32px 80px}header{max-width:1050px}.eyebrow{font:600 12px/1.4 ui-monospace,monospace;letter-spacing:.08em;color:var(--accent)}h1{font-size:clamp(32px,4vw,54px);font-weight:650;letter-spacing:-.045em;line-height:1.08;margin:18px 0}h2{font-size:27px;letter-spacing:-.025em;margin:0 0 12px}h3{font-size:19px;margin:28px 0 8px}p{max-width:1040px;margin:10px 0 18px}a{color:var(--accent);text-underline-offset:3px}nav{display:flex;gap:20px;flex-wrap:wrap;padding:22px 0;border-bottom:1px solid var(--line)}section{margin-top:44px;scroll-margin-top:20px}.stats{display:flex;gap:40px;flex-wrap:wrap;margin:28px 0}.stats strong{display:block;font-size:30px;line-height:1.2;font-variant-numeric:tabular-nums}.stats span{color:var(--muted);font-size:13px}.table-scroll{overflow:auto;border:1px solid var(--line);background:white}table{border-collapse:collapse;width:100%;text-align:left;font-size:13px}th,td{padding:13px 14px;border-bottom:1px solid var(--line);vertical-align:top}thead th{background:#e9efe8;color:#42534a;font-size:12px;font-weight:600;white-space:nowrap}tbody tr:last-child>*{border-bottom:0}td small,th small{display:block;color:var(--muted);font-weight:400;margin-top:4px;font-size:11px;max-width:240px}tbody tr:hover{background:#fafcf9}.host-table{max-height:820px}.host-table thead th{position:sticky;top:0;z-index:1}.host-table th[scope=row]{min-width:245px;max-width:340px;overflow-wrap:anywhere;font-weight:500}.host-table td{min-width:215px;max-width:290px}.badges{display:flex;flex-wrap:wrap;gap:5px}.badge{display:inline-block;border-radius:4px;padding:3px 6px;background:#ecefeb;font:12px/1.5 ui-monospace,monospace;white-space:normal}.badge b{font-weight:500;opacity:.65}.badge.ok{background:#e5f4e9;color:#175b34}.badge.redirect{background:#eef1fa;color:#405282}.badge.error{background:#fff0ee;color:#9b3c30}.badge.other{background:#faf0da;color:#785315}.outside{color:#87938c;font-style:italic}summary{cursor:pointer;color:var(--accent);font-size:12px;margin-top:8px}details[open]>summary{margin-bottom:10px}.observation{margin-top:15px;max-width:285px;overflow-wrap:anywhere}.observation strong{font-size:12px}dl{margin:5px 0 0;font-size:11px}dt{color:var(--muted);margin-top:7px}dd{margin:0}code{font-size:12px;overflow-wrap:anywhere}li{margin:8px 0;max-width:1080px}.filters{display:flex;gap:16px;align-items:end;flex-wrap:wrap;margin:22px 0 12px}.filters label{font-size:12px;color:var(--muted)}input,select{display:block;padding:10px 12px;border:1px solid #b9c8be;background:#fff;border-radius:4px;color:var(--ink);font:14px system-ui;margin-top:5px}input{width:min(380px,80vw)}output{color:var(--muted);font-size:13px;padding-bottom:10px}input:focus,select:focus,summary:focus,a:focus{outline:2px solid var(--accent);outline-offset:3px}#diagnostica>details{background:white;border:1px solid var(--line);padding:12px 16px;margin:10px 0}#diagnostica summary{font-size:14px;margin:0}footer{margin-top:50px;border-top:1px solid var(--line);padding-top:20px;color:var(--muted);font-size:12px}@media(max-width:700px){main{padding:28px 16px}.stats{gap:22px}nav{gap:12px}section{margin-top:32px}.host-table{max-height:70vh}}@media print{body{background:#fff}main{padding:0}.filters,nav{display:none}.table-scroll,.host-table{overflow:visible;max-height:none}details{break-inside:avoid}a{color:inherit}}
"""

SCRIPT = """
const query=document.getElementById('query'),filter=document.getElementById('filter'),rows=[...document.querySelectorAll('#targets tbody tr')],visible=document.getElementById('visible');
function applyFilters(){const needle=query.value.trim().toLocaleLowerCase('it'),mode=filter.value;let count=0;for(const row of rows){const show=row.dataset.search.includes(needle)&&(mode==='all'||row.dataset[mode]==='1');row.hidden=!show;if(show)count++;}visible.textContent=count+' / '+rows.length+' URL';}
query.addEventListener('input',applyFilters);filter.addEventListener('change',applyFilters);
"""

STYLE += '.finding-warning{background:#fff7e5;border-left:4px solid #b4812b;padding:16px 22px;margin:24px 0}.finding-warning h3{margin:0 0 8px}.finding-warning li{margin:6px 0}'


def render(runs, targets, output, dataset):
    target_map = {target["id"]: target for target in targets}
    for run in runs:
        run["partial"] = set(run["rows"]["upstream"]) != set(target_map)
        for arm in ARMS:
            for target_id, row in run["rows"][arm].items():
                if target_id not in target_map or row["url"] != target_map[target_id]["url"]:
                    raise ValueError(f"Run target differs from canonical dataset: {run['name']}/{target_id}")
    baselines, repeated, changed = repeated_deltas(runs, targets)
    times = [datetime.fromisoformat(run["metadata"]["started_at"]).astimezone(ZoneInfo("Europe/Rome")) for run in runs]
    date = min(times).strftime("%d/%m/%Y")
    groups = len({target.get("group", "") for target in targets})
    repeated_text = str(len(repeated)) if baselines else "—"
    body = '<header><div class="eyebrow">BENCHMARK · ' + esc(date) + ' · EUROPE/ROME</div><h1>httpx e<br>undetected-httpx 2.0</h1><p>Confronto degli output su siti pubblici e sottodomini: risposte HTTP, contenuti, redirect, errori e tempi. I dati di ogni esecuzione restano consultabili accanto al report.</p><div class="stats"><div><strong>' + str(len(targets)) + '</strong><span>URL nel dataset</span></div><div><strong>' + str(groups) + '</strong><span>gruppi di siti</span></div><div><strong>' + str(len(runs)) + '</strong><span>esecuzioni A/B</span></div><div><strong>' + repeated_text + '</strong><span>differenze ripetute AB / BA</span></div></div></header><nav aria-label="Sezioni"><a href="#risultati">Risultati</a><a href="#ripetizione">Ripetizione</a><a href="#url">Tutti gli URL</a><a href="#diagnostica">Diagnostica</a><a href="#metodo">Metodo e dati</a></nav>'
    body += findings_section(runs) + summary_section(runs) + repeated_section(baselines, repeated, changed, targets)
    body += target_section(runs, targets, repeated) + diagnostics_section(runs, output)
    body += method_section(runs, output, dataset)
    body += '<footer>Report locale: nessun font, libreria, script o servizio esterno. Le connessioni esterne partono solo quando apri un link a un sito.</footer>'
    return '<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>httpx vs undetected-httpx 2.0 · ' + esc(date) + '</title><style>' + STYLE + '</style></head><body><main>' + body + '</main><script>' + SCRIPT + '</script></body></html>\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Directory containing targets.csv and completed run directories")
    parser.add_argument("--runs", nargs="+", help="Explicit run directory names, in display order; default: discover completed captures")
    parser.add_argument("--output", help="HTML path; default: ROOT/index.html")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else root / "index.html"
    try:
        dataset = root / "targets.csv"
        targets = read_targets(dataset)
        paths = [root / name for name in args.runs] if args.runs else sorted(path for path in root.iterdir() if path.is_dir() and (path / "summary.json").exists() and not (path / "INVALIDATED.md").exists())
        if not paths:
            raise ValueError("No completed captures found")
        runs = [load_run(path) for path in paths]
        output.write_text(render(runs, targets, output, dataset), encoding="utf-8")
        print(output)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print("render_httpx_comparison: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
