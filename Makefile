GO ?= go
BINARY := bin/undetected-httpx

.PHONY: build install test test-upstream fmt snapshot clean

build:
	$(GO) build -trimpath -o $(BINARY) ./cmd/undetected-httpx

install:
	$(GO) install ./cmd/undetected-httpx

# Compile all packages and run local regressions for the fork.
test:
	$(GO) test -timeout 2m ./... -run 'Test(Cloak|HTTPCloak|CloudUploadEnvironment|Browser|NativeHTTP)'

# The inherited suite includes requests to public websites.
test-upstream:
	$(GO) test -timeout 10m ./...

fmt:
	gofmt -w cmd common examples internal runner

snapshot:
	goreleaser release --snapshot --clean

clean:
	rm -rf bin dist
