package runner

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBrowserRunnerLocalProbe(t *testing.T) {
	requests := make(chan http.Header, 4)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests <- r.Header.Clone()
		w.Header().Set("Content-Type", "text/html")
		_, _ = fmt.Fprint(w, "<!doctype html><html><title>Browser probe</title><body>ready</body></html>")
	}))
	defer server.Close()

	var mu sync.Mutex
	var results []Result
	options := &Options{
		Threads:                   1,
		RateLimit:                 10,
		Timeout:                   5,
		Delay:                     -1,
		RandomAgent:               true,
		ExtractTitle:              true,
		NoFallbackScheme:          true,
		DisableStdin:              true,
		DisableStdout:             true,
		MaxResponseBodySizeToRead: 1 << 20,
		MaxResponseBodySizeToSave: 1 << 20,
		InputTargetHost:           []string{server.URL},
		OnResult: func(result Result) {
			mu.Lock()
			defer mu.Unlock()
			results = append(results, result)
		},
	}

	runner, err := New(options)
	require.NoError(t, err)
	defer runner.Close()
	runner.RunEnumeration()

	mu.Lock()
	defer mu.Unlock()
	require.Len(t, results, 1)
	require.NoError(t, results[0].Err)
	require.Equal(t, http.StatusOK, results[0].StatusCode)
	require.Equal(t, "Browser probe", results[0].Title)
	require.Equal(t, server.URL, results[0].URL)
	select {
	case headers := <-requests:
		require.Contains(t, headers.Get("User-Agent"), "Chrome/")
		require.NotEqual(t, "close", headers.Get("Connection"))
	default:
		t.Fatal("the local server received no browser request")
	}
}

func TestBrowserTransportRejectsNativeFeaturesBeforeStartup(t *testing.T) {
	options := &Options{
		Unsafe:                true,
		SniName:               "custom.example",
		TechDetect:            true,
		CustomFingerprintFile: "missing-fingerprints.json",
	}

	runner, err := New(options)
	require.Nil(t, runner)
	require.EqualError(t, err, "browser transport does not support -unsafe, -sni-name; use -native-http for these features")
}

func TestNativeHTTPTransportPreservesNetworkAndProbeOptions(t *testing.T) {
	options := &Options{
		NativeHTTP:  true,
		Threads:     1,
		Unsafe:      true,
		SniName:     "custom.example",
		Resolvers:   []string{"127.0.0.1:53"},
		Allow:       []string{"192.0.2.0/24"},
		TLSGrab:     true,
		ProbeAllIPS: true,
		OutputIP:    true,
	}

	require.NoError(t, options.ValidateOptions())
}

func TestBrowserTransportRejectsNetworkPolicyAndTLSMetadata(t *testing.T) {
	options := &Options{
		Threads:   1,
		TLSGrab:   true,
		TLSProbe:  true,
		Resolvers: []string{"127.0.0.1:53"},
		Allow:     []string{"192.0.2.0/24"},
	}

	require.EqualError(t, options.ValidateOptions(), "browser transport does not support -tls-grab, -tls-probe, -resolvers, -allow; use -native-http for these features")
}

func TestBrowserTransportProtocolCompatibility(t *testing.T) {
	for _, test := range []struct {
		name       string
		protocol   string
		nativeHTTP bool
		valid      bool
	}{
		{name: "browser-negotiation", valid: true},
		{name: "browser-http11", protocol: "http11", valid: true},
		{name: "browser-http2", protocol: "HTTP2", valid: true},
		{name: "browser-http3-unavailable", protocol: "http3"},
		{name: "native-http11", protocol: "http11", nativeHTTP: true, valid: true},
		{name: "native-http2-unavailable", protocol: "http2", nativeHTTP: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			options := &Options{Threads: 1, Protocol: test.protocol, NativeHTTP: test.nativeHTTP}
			err := options.ValidateOptions()
			if test.valid {
				require.NoError(t, err)
			} else {
				require.ErrorContains(t, err, "invalid protocol")
			}
			if test.name == "browser-http2" {
				require.Equal(t, "http2", options.Protocol)
			}
		})
	}
}
