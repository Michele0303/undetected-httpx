package cli

import (
	"testing"

	"github.com/Michele0303/undetected-httpx/v2/internal/pdcp"
	"github.com/Michele0303/undetected-httpx/v2/runner"
)

func TestCloudUploadEnvironmentDoesNotEnableUploads(t *testing.T) {
	previous := pdcp.EnableCloudUpload
	pdcp.EnableCloudUpload = true
	t.Cleanup(func() { pdcp.EnableCloudUpload = previous })

	opts := &runner.Options{}
	if writer := setupOptionalAssetUpload(opts); writer != nil {
		t.Fatal("cloud upload requires explicit options")
	}
	if opts.OnResult != nil || opts.OnClose != nil {
		t.Fatal("cloud upload callbacks must remain unset without explicit options")
	}
}
