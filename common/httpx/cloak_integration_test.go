package httpx

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/projectdiscovery/fastdialer/fastdialer"
	"github.com/projectdiscovery/networkpolicy"
	"github.com/stretchr/testify/require"
)

func cloakTestClient(t *testing.T, configure func(*Options)) *HTTPX {
	t.Helper()
	opts := DefaultOptions
	opts.CdnCheck = "false"
	opts.RetryMax = 0
	opts.Timeout = 2 * time.Second
	if configure != nil {
		configure(&opts)
	}
	client, err := New(&opts)
	require.NoError(t, err)
	t.Cleanup(client.Close)
	return client
}

func TestCloakIntegrationRedirectsAndHeaders(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/start" {
			w.Header().Set("Location", "/final")
			w.WriteHeader(http.StatusFound)
			return
		}
		require.Contains(t, r.UserAgent(), "Chrome/")
		require.Empty(t, r.Header.Get("Accept-Charset"))
		require.Equal(t, []string{"one", "two"}, r.Header.Values("X-Test"))
		cookie, err := r.Cookie("session")
		require.NoError(t, err)
		require.Equal(t, "value", cookie.Value)
		_, _ = io.WriteString(w, "<title>Browser client</title>\nhello world")
	}))
	defer server.Close()
	for _, follow := range []bool{false, true} {
		t.Run(fmt.Sprint(follow), func(t *testing.T) {
			client := cloakTestClient(t, func(o *Options) {
				o.FollowRedirects = follow
				o.CustomHeaders = map[string][]string{"X-Test": {"one", "two"}, "Cookie": {"session=value"}}
			})
			require.Same(t, client.client.HTTPClient, client.client.HTTPClient2)
			require.Same(t, client.client.HTTPClient, client.client2)
			req, err := client.NewRequest(http.MethodGet, server.URL+"/start")
			require.NoError(t, err)
			client.SetCustomHeaders(req, client.CustomHeaders)
			resp, err := client.Do(req, UnsafeOptions{})
			require.NoError(t, err)
			if follow {
				require.Equal(t, http.StatusOK, resp.StatusCode)
				require.Contains(t, string(resp.Data), "Browser client")
				require.NotEmpty(t, resp.Chain)
			} else {
				require.Equal(t, http.StatusFound, resp.StatusCode)
			}
		})
	}
}

func TestCloakIntegrationPostAndCustomAgent(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/redirect" {
			w.Header().Set("Location", "/echo")
			w.WriteHeader(http.StatusTemporaryRedirect)
			return
		}
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "explicit-agent", r.UserAgent())
		_, _ = io.Copy(w, r.Body)
	}))
	defer server.Close()
	client := cloakTestClient(t, func(o *Options) { o.FollowRedirects = true })
	req, err := client.NewRequest(http.MethodPost, server.URL+"/redirect")
	require.NoError(t, err)
	require.NoError(t, req.SetBody([]byte("payload")))
	client.SetCustomHeaders(req, map[string][]string{"User-Agent": {"explicit-agent"}})
	resp, err := client.Do(req, UnsafeOptions{})
	require.NoError(t, err)
	require.Equal(t, "payload", string(resp.Data))
}

func TestCloakIntegrationBodyLimitClosesStream(t *testing.T) {
	closed := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		_, _ = io.WriteString(w, strings.Repeat("a", 8192))
		w.(http.Flusher).Flush()
		<-r.Context().Done()
		close(closed)
	}))
	defer server.Close()
	client := cloakTestClient(t, func(o *Options) { o.MaxResponseBodySizeToRead = 64 })
	req, err := client.NewRequest(http.MethodGet, server.URL)
	require.NoError(t, err)
	resp, err := client.Do(req, UnsafeOptions{})
	require.NoError(t, err)
	require.Len(t, resp.Data, 64)
	select {
	case <-closed:
	case <-time.After(3 * time.Second):
		t.Fatal("limited read left the upstream connection open")
	}
}

func TestCloakIntegrationRejectsUnsupportedOptions(t *testing.T) {
	for name, configure := range map[string]func(*Options){
		"unsafe":          func(o *Options) { o.Unsafe = true },
		"sni":             func(o *Options) { o.SniName = "example.com" },
		"ztls":            func(o *Options) { o.ZTLS = true },
		"tls-grab":        func(o *Options) { o.TLSGrab = true },
		"exclude-cdn":     func(o *Options) { o.ExcludeCdn = true },
		"tls-impersonate": func(o *Options) { o.TlsImpersonate = "chrome" },
		"resolvers":       func(o *Options) { o.Resolvers = []string{"127.0.0.1:53"} },
		"policy":          func(o *Options) { o.NetworkPolicy = &networkpolicy.NetworkPolicy{} },
		"http3":           func(o *Options) { o.Protocol = HTTP3 },
	} {
		t.Run(name, func(t *testing.T) {
			opts := DefaultOptions
			configure(&opts)
			_, err := New(&opts)
			require.Error(t, err)
		})
	}
	client := cloakTestClient(t, nil)
	ctx := context.WithValue(context.Background(), fastdialer.IP, "127.0.0.1")
	_, err := client.NewRequestWithContext(ctx, http.MethodGet, "http://example.com")
	require.ErrorContains(t, err, "--native-http")
}
