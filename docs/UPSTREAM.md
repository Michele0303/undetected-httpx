# Upstream provenance

We imported the Go scanner from [ProjectDiscovery httpx](https://github.com/projectdiscovery/httpx), tag [`v1.12.0`](https://github.com/projectdiscovery/httpx/tree/v1.12.0), commit [`4b6a9a9d476f94a4f3a630f37051f5671ecfb1f8`](https://github.com/projectdiscovery/httpx/commit/4b6a9a9d476f94a4f3a630f37051f5671ecfb1f8).

The default transport uses [sardanioss/httpcloak](https://github.com/sardanioss/httpcloak), version `v1.7.3`. `go.mod` and `go.sum` record the dependency versions and checksums.

The fork uses the Go module path `github.com/Michele0303/undetected-httpx/v2`. The main executable is `undetected-httpx`; `cmd/httpx` provides a compatibility name through the same entry point.

Fork changes include the HTTPCloak transport adapter, browser/native transport flags, transport compatibility validation, version branding, disabled upstream update behavior, and explicit cloud-upload activation. We kept the upstream probing and output code to preserve its behavior where the chosen transport supports it.

The original Python version 0.4.0 remains under `legacy/python`. Its README documents that implementation.

## Licenses

- [LICENSE.md](../LICENSE.md) retains ProjectDiscovery's MIT license and copyright notice.
- [LICENSE](../LICENSE) retains the original undetected-httpx MIT license and copyright notice.
- [HTTPCloak's license](https://github.com/sardanioss/httpcloak/blob/main/LICENSE) covers that dependency. Consult the dependencies' own license files for their terms.

No workflow publishes artifacts to ProjectDiscovery. The GoReleaser configuration creates local packages with publishing disabled.
