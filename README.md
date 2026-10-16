# undetected-httpx 2.0

HTTP probing with ProjectDiscovery's [httpx](https://github.com/projectdiscovery/httpx) engine and [HTTPCloak](https://github.com/sardanioss/httpcloak) browser transport. Version 2.0 is a Go fork of httpx v1.12.0. It replaces the main request transport with HTTPCloak and keeps the upstream probe pipeline, retry wrapper, and output formats.

HTTPCloak supplies browser TLS and HTTP fingerprints. The default profile is `chrome-latest`. Browser impersonation does not guarantee access to a site or make traffic undetectable. Server policies, IP reputation, JavaScript challenges, and request behavior can still affect results.

This repository contains `v2.0.0-dev`. The previous Python CLI, version 0.4.0, lives in [legacy/python](legacy/python). Read the [migration notes](docs/V2-MIGRATION.md) before replacing an existing installation.

## Selected 403 → 200 results

<table>
  <tr>
    <th>httpx v1.12.0</th>
    <th>undetected-httpx 2.0</th>
  </tr>
  <tr>
    <td width="50%"><img src="docs/demos/v2-live/capture/upstream/httpx.gif" alt="Live execution of httpx returning HTTP 403 on five selected URLs" width="100%"></td>
    <td width="50%"><img src="docs/demos/v2-live/capture/fork/undetected-httpx.gif" alt="Live execution of undetected-httpx 2.0 returning HTTP 200 on the same five URLs" width="100%"></td>
  </tr>
</table>

**Real executions recorded with VHS on 16 October 2026**, using the same five selected URLs and User-Agent. Both binaries run in the terminal; the GIFs retain their actual output and timing. The fork's saved responses have page titles without known challenge indicators in these cases. See the [full 96-host comparison](docs/benchmarks/2026-10-16/README.md) for the complete results and remaining limitations.

[Watch the MP4 comparison](docs/demos/v2-live/comparison.mp4) · [Recording scripts, responses and reproduction](docs/demos/v2-live/README.md)

## Build

Install Go 1.26.0 or newer, then build from this checkout:

```sh
git clone --branch mf/v2-httpcloak https://github.com/Michele0303/undetected-httpx.git
cd undetected-httpx
make build
./bin/undetected-httpx -version
```

Use `make install` to place `undetected-httpx` in your Go binary directory. To build the compatibility executable named `httpx`, run `go build -o bin/httpx ./cmd/httpx`.

## Probe

```sh
# Read targets from stdin and print status codes and titles.
printf '%s\n' https://example.com | ./bin/undetected-httpx -sc -title

# Choose a browser profile and write JSONL.
./bin/undetected-httpx -u https://example.com --browser chrome-latest -json

# Use the upstream transport for probes that need direct network control.
./bin/undetected-httpx -u https://example.com --native-http -tls-grab -ip

# Show the full upstream-compatible flag list.
./bin/undetected-httpx -h
```

`-impersonate` aliases `--browser`. HTTPCloak handles browser headers and the User-Agent for normal requests; a User-Agent supplied through `-H` overrides that choice. `--protocol http11` forces HTTP/1.1; `--protocol http2` requires HTTPS and HTTP/2 support. The default negotiates HTTP/2 and falls back to HTTP/1.1 when the server does not offer it. This adapter does not use HTTP/3.

Several low-level flags require `--native-http`, including `--unsafe`, custom resolvers, TLS certificate probes, and explicit IP/network policy options. The CLI rejects unsupported combinations. See the [compatibility table](docs/V2-MIGRATION.md#transport-compatibility).

The fork disables upstream self-update and background update checks. Cloud uploads require explicit dashboard/upload options; an environment variable alone does not enable uploads.

## Measured comparison

On 16 October 2026, we compared upstream v1.12.0 with this fork on **96 public hosts across 32 site groups**, including documentation, support, community, and status subdomains. Five A/B runs produced 960 observations, with no missing output or request failures. Each run used three initial probes per second and no configured retries.

| Test, 96 URLs per tool | Upstream | Fork |
|---|---:|---:|
| Same explicit Chrome User-Agent: HTTP 403 | 8 | 1 |
| Follow up to two redirects: HTTP 2xx | 82 | 93 |
| Follow up to two redirects: HTTP 403 / 406 | 9 / 4 | 2 / 0 |
| Native transport control: HTTP 2xx | 61 | 61 |

HTTP 2xx does **not** mean usable content: the fork received `200` challenge pages from Reddit and Mozilla Support. Stack Overflow and Tripadvisor still returned `403` after redirects. Eight baseline status differences repeated with the execution order reversed; the native control differed on one host, showing that site behavior can change between requests. These observations do not establish undetectability or isolate TLS fingerprints from other transport differences.

Read the [findings and reproduction instructions](docs/benchmarks/2026-10-16/README.md), open the [searchable HTML report](docs/benchmarks/2026-10-16/index.html) locally, or inspect the [code validation results](docs/benchmarks/2026-10-16/validation.md). Each run includes JSONL responses, normalized CSV, commands, timestamps, and binary hashes. Published response data omits client IPs and session tokens, as documented in the report.

## Development

```sh
make test           # Compile all packages and run local fork regressions
make test-upstream  # Include inherited tests that contact public websites
make snapshot       # Package local archives with GoReleaser v2
```

CI builds both CLI names and runs the local regressions on Linux and macOS. The Docker image builds the Go binary and includes a CA certificate bundle:

```sh
docker build -t undetected-httpx:dev .
docker run --rm undetected-httpx:dev -u https://example.com -sc -title
```

See [upstream provenance](docs/UPSTREAM.md) for the source revisions and licenses.
