package main

import "github.com/Michele0303/undetected-httpx/v2/internal/cli"

// Keep the upstream executable name for scripts that already invoke httpx.
func main() {
	cli.Run()
}
