# Migrating to version 2.0

Version 2.0 replaces the Python wrapper with a Go fork of ProjectDiscovery httpx v1.12.0. The default request transport uses HTTPCloak. The earlier Python implementation remains in `legacy/python` with its original dependency files and README.

## Installation and scripts

Build with Go 1.26.0 or newer:

```sh
make build
./bin/undetected-httpx -h
```

Update scripts to invoke this binary. Python package installation and Python imports do not install or load the Go implementation. The Go library module is `github.com/Michele0303/undetected-httpx/v2`; its `runner` and `common/httpx` packages retain the upstream Go API with transport options added by this fork.

Both `cmd/undetected-httpx` and `cmd/httpx` call the same CLI entry point. Install the `httpx` alias only if you want to replace an existing executable with that name.

The new CLI uses the upstream httpx options. Review `-h` instead of assuming Python flags have the same meaning. Use `--browser chrome-latest` or `-impersonate chrome-latest` to choose a profile, and `--native-http` to select the upstream transport.

## Transport compatibility

| Behavior | Default HTTPCloak transport | `--native-http` |
| --- | --- | --- |
| Browser TLS/HTTP fingerprint | HTTPCloak profile, default `chrome-latest` | Upstream behavior |
| Retry wrapper and probe/output pipeline | Retained | Retained |
| `--protocol` | `http11`, or `http2` over HTTPS | `http11` |
| Random User-Agent | Browser preset takes precedence | Upstream behavior |
| Explicit `-H 'User-Agent: ...'` | Overrides preset User-Agent | Supported |
| `--unsafe`, `--pipeline`, `--jarm` | Rejected | Upstream behavior |
| `--sni-name`, `--ztls`, `--tls-impersonate` | Rejected | Upstream behavior |
| `--tls-grab`, `--tls-probe` | Rejected | Upstream behavior |
| `--resolvers`, `--allow`, `--deny`, `--exclude`, `--probe-all-ips` | Rejected | Upstream behavior |
| `--ip`, `--asn`, `--cdn`, `--match-cdn`, `--filter-cdn` | Rejected | Upstream behavior |
| Custom `Networkpolicy` through Go API | Rejected | Upstream behavior |

HTTPCloak owns connection establishment in browser mode. The upstream dialer's DNS, IP selection, and network restrictions cannot govern those connections. Use `--native-http` when your scan depends on those controls or their metadata.

The default transport negotiates HTTP/2 over HTTPS and falls back to HTTP/1.1 when the server does not offer HTTP/2. `--protocol http2` requires HTTPS and HTTP/2 support; it does not support cleartext HTTP/2. This adapter does not use HTTPCloak's HTTP/3 support.

Browser mode supports HTTP, HTTPS, SOCKS5, and SOCKS5H proxies, including proxy environment variables. It keeps the standard Go client's redirect and cookie handling, supports an explicit Host header, and decodes gzip, deflate, Brotli, and Zstandard responses as streams.

TLS certificate output requires native mode because HTTPCloak does not expose consistent certificate metadata across HTTP/1.1 and HTTP/2. Auxiliary tools, such as the screenshot browser, have their own network behavior; changing the main transport does not give them the selected HTTPCloak fingerprint.

HTTPCloak streams responses into the existing httpx processing path. The scanner still applies its response read limits. Browser impersonation does not guarantee that a target accepts the request or removes its anti-bot checks. The transport does not execute JavaScript or simulate browser interactions.

## Updates and optional uploads

The CLI does not check for upstream releases in the background. `-update` prints an installation message without replacing the fork with ProjectDiscovery's binary.

Cloud uploads require explicit dashboard/upload options. Setting an upstream cloud-upload environment variable alone does not turn them on. The optional ProjectDiscovery dashboard integration still uses its existing credential setup when you request an upload.

## Validation

Run `make test` for local fork regression tests and compilation of all packages. Run `make test-upstream` to include the inherited suite; some tests request public websites and can fail because of network conditions or remote changes. CI runs the local tests on Linux and macOS.
