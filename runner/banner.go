package runner

import (
	"github.com/projectdiscovery/gologger"
	"github.com/projectdiscovery/utils/auth/pdcp"
)

const banner = `undetected-httpx`

// Version is the current version of undetected-httpx.
const Version = `v2.0.0-dev`

// showBanner is used to show the banner to the user
func showBanner() {
	gologger.Print().Msgf("%s %s\n", banner, Version)
	gologger.Print().Msg("ProjectDiscovery httpx probes with HTTPCloak browser transport\n")
}

// GetUpdateCallback preserves the upstream flag without replacing this fork.
func GetUpdateCallback() func() {
	return func() {
		gologger.Warning().Msg("Self-update is unavailable for this fork; install a new undetected-httpx release.")
	}
}

// AuthWithPDCP is used to authenticate with PDCP
func AuthWithPDCP() {
	showBanner()
	pdcp.CheckNValidateCredentials("httpx")
}
