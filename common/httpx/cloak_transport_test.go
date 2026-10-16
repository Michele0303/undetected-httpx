package httpx

import (
	"bytes"
	"compress/flate"
	"compress/gzip"
	"compress/zlib"
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/cookiejar"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/andybalholm/brotli"
	"github.com/klauspost/compress/zstd"
	"github.com/projectdiscovery/fastdialer/fastdialer"
)

func testCloakClient(t *testing.T, protocol Proto) *http.Client {
	t.Helper()
	transport, err := newCloakTransport("chrome-latest", "", protocol)
	if err != nil {
		t.Fatal(err)
	}
	// Tests never use a developer's environment proxy.
	transport.proxy = func(*http.Request) (*url.URL, error) { return nil, nil }
	t.Cleanup(transport.Close)
	return &http.Client{Transport: transport, Timeout: 5 * time.Second}
}

func TestCloakTransportRequestAndResponse(t *testing.T) {
	for _, mode := range []string{"http", "tls-h1", "tls-h2"} {
		t.Run(mode, func(t *testing.T) {
			type received struct {
				host, ua, body, hint string
				proto                int
				tags                 []string
			}
			requests := make(chan received, 1)
			server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				body, _ := io.ReadAll(r.Body)
				requests <- received{r.Host, r.UserAgent(), string(body), r.Header.Get("Sec-Ch-Ua"), r.ProtoMajor, r.Header.Values("X-Tag")}
				w.Header().Add("Set-Cookie", "one=1")
				w.Header().Add("Set-Cookie", "two=2")
				w.Header().Set("X-Result", "ok")
				_, _ = io.WriteString(w, "response")
			}))
			if mode == "http" {
				server.Start()
			} else {
				server.EnableHTTP2 = mode == "tls-h2"
				server.StartTLS()
			}
			defer server.Close()
			client := testCloakClient(t, UNKNOWN)
			req, _ := http.NewRequest(http.MethodPost, server.URL+"/test?q=1", strings.NewReader("payload"))
			req.Host = "virtual.example"
			req.Header["X-Tag"] = []string{"first", "second"}
			response, err := client.Do(req)
			if err != nil {
				t.Fatal(err)
			}
			defer response.Body.Close()
			body, err := io.ReadAll(response.Body)
			if err != nil || string(body) != "response" {
				t.Fatalf("body=%q err=%v", body, err)
			}
			got := <-requests
			if got.host != "virtual.example" || got.body != "payload" || !strings.Contains(got.ua, "Chrome/") || got.hint == "" {
				t.Fatalf("request: %+v", got)
			}
			if len(got.tags) != 2 || got.tags[0] != "first" || got.tags[1] != "second" {
				t.Fatalf("headers: %v", got.tags)
			}
			wantProto := 1
			if mode == "tls-h2" {
				wantProto = 2
			}
			if got.proto != wantProto || response.ProtoMajor != wantProto {
				t.Fatalf("protocol: request=%d response=%d", got.proto, response.ProtoMajor)
			}
			if mode == "tls-h2" && (response.TLS == nil || len(response.TLS.PeerCertificates) == 0) {
				t.Fatal("HTTP/2 TLS metadata lost in the response bridge")
			}
			if response.Header.Get("X-Result") != "ok" || len(response.Cookies()) != 2 {
				t.Fatalf("response headers: %v", response.Header)
			}
			if req.Header.Get("User-Agent") != "" {
				t.Fatal("transport mutated caller headers")
			}
		})
	}
}

func TestCloakTransportBodylessCompressedResponses(t *testing.T) {
	for _, status := range []int{http.StatusOK, http.StatusNoContent, http.StatusNotModified} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Encoding", "gzip")
			w.WriteHeader(status)
		}))
		client := testCloakClient(t, UNKNOWN)
		for _, method := range []string{http.MethodHead, http.MethodGet} {
			req, _ := http.NewRequest(method, server.URL, nil)
			response, err := client.Do(req)
			if err != nil {
				server.Close()
				t.Fatalf("%s status %d: %v", method, status, err)
			}
			body, err := io.ReadAll(response.Body)
			_ = response.Body.Close()
			if err != nil || len(body) != 0 {
				t.Fatalf("%s status %d: body=%q err=%v", method, status, body, err)
			}
		}
		server.Close()
	}
}

func TestCloakTransportForcedHTTP2(t *testing.T) {
	for _, tlsServer := range []bool{false, true} {
		server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("forced H2 sent an H1 request") }))
		if tlsServer {
			server.StartTLS()
		} else {
			server.Start()
		}
		client := testCloakClient(t, HTTP2)
		response, err := client.Get(server.URL)
		if err == nil {
			response.Body.Close()
			t.Fatal("forced H2 accepted an H1 origin")
		}
		server.Close()
	}
}

func TestCloakTransportDecodesCompressedBody(t *testing.T) {
	for _, encoding := range []string{"gzip", "deflate", "raw-deflate", "br", "zstd"} {
		t.Run(encoding, func(t *testing.T) {
			var compressed bytes.Buffer
			var encoder io.WriteCloser
			switch encoding {
			case "gzip":
				encoder = gzip.NewWriter(&compressed)
			case "deflate":
				encoder = zlib.NewWriter(&compressed)
			case "raw-deflate":
				encoder, _ = flate.NewWriter(&compressed, flate.DefaultCompression)
			case "br":
				encoder = brotli.NewWriter(&compressed)
			case "zstd":
				encoder, _ = zstd.NewWriter(&compressed)
			}
			_, _ = io.WriteString(encoder, "decoded content")
			_ = encoder.Close()
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Encoding", strings.TrimPrefix(encoding, "raw-"))
				_, _ = w.Write(compressed.Bytes())
			}))
			defer server.Close()
			response, err := testCloakClient(t, UNKNOWN).Get(server.URL)
			if err != nil {
				t.Fatal(err)
			}
			defer response.Body.Close()
			body, err := io.ReadAll(response.Body)
			if err != nil || string(body) != "decoded content" || !response.Uncompressed || response.Header.Get("Content-Encoding") != "" || response.ContentLength != -1 {
				t.Fatalf("body=%q err=%v uncompressed=%v headers=%v", body, err, response.Uncompressed, response.Header)
			}
		})
	}
}

func TestCloakTransportCompressedStreamLimit(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Encoding", "gzip")
		zw := gzip.NewWriter(w)
		_, _ = io.WriteString(zw, strings.Repeat("x", 1<<20))
		_ = zw.Flush()
		w.(http.Flusher).Flush()
		<-r.Context().Done()
	}))
	defer server.Close()
	response, err := testCloakClient(t, UNKNOWN).Get(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 64))
	if err != nil || len(body) != 64 {
		t.Fatalf("limited response len=%d err=%v", len(body), err)
	}
	closed := make(chan struct{})
	go func() { _ = response.Body.Close(); close(closed) }()
	select {
	case <-closed:
	case <-time.After(time.Second):
		t.Fatal("compressed body Close waited for the complete response")
	}
}

func TestCloakTransportRedirectCookieAndReplay(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/start" {
			http.SetCookie(w, &http.Cookie{Name: "session", Value: "present", Path: "/"})
			w.Header().Set("Location", "/final")
			w.WriteHeader(http.StatusTemporaryRedirect)
			return
		}
		body, _ := io.ReadAll(r.Body)
		_, _ = io.WriteString(w, r.Method+"|"+string(body)+"|"+r.Header.Get("Cookie"))
	}))
	defer server.Close()
	client := testCloakClient(t, UNKNOWN)
	client.Jar, _ = cookiejar.New(nil)
	response, err := client.Post(server.URL+"/start", "text/plain", strings.NewReader("replay"))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil || string(body) != "POST|replay|session=present" {
		t.Fatalf("redirect response=%q err=%v", body, err)
	}
}

func TestCloakTransportStreamCancellation(t *testing.T) {
	for _, h2 := range []bool{false, true} {
		t.Run(map[bool]string{false: "h1", true: "h2"}[h2], func(t *testing.T) {
			cancelled := make(chan struct{}, 1)
			server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_, _ = io.WriteString(w, "first")
				w.(http.Flusher).Flush()
				<-r.Context().Done()
				cancelled <- struct{}{}
			}))
			if h2 {
				server.EnableHTTP2 = true
				server.StartTLS()
			} else {
				server.Start()
			}
			defer server.Close()
			client := testCloakClient(t, UNKNOWN)
			response, err := client.Get(server.URL)
			if err != nil {
				t.Fatal(err)
			}
			first := make([]byte, 5)
			if _, err := io.ReadFull(response.Body, first); err != nil {
				t.Fatal(err)
			}
			closed := make(chan struct{})
			go func() { _ = response.Body.Close(); close(closed) }()
			select {
			case <-closed:
			case <-time.After(time.Second):
				t.Fatal("Close drained or blocked on the unread body")
			}
			select {
			case <-cancelled:
			case <-time.After(time.Second):
				t.Fatal("server did not see cancellation")
			}
		})
	}
}

func TestCloakTransportContextDeadline(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() }))
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, server.URL, nil)
	_, err := testCloakClient(t, UNKNOWN).Do(req)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected context deadline, got %v", err)
	}
}

func TestCloakTransportProxyCONNECT(t *testing.T) {
	var connectCount atomic.Int32
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { _, _ = io.WriteString(w, "proxied") }))
	defer origin.Close()
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodConnect {
			t.Errorf("proxy method %s", r.Method)
			http.Error(w, "CONNECT required", 400)
			return
		}
		connectCount.Add(1)
		upstream, err := net.Dial("tcp", r.Host)
		if err != nil {
			http.Error(w, "dial failed", 502)
			return
		}
		conn, _, err := w.(http.Hijacker).Hijack()
		if err != nil {
			upstream.Close()
			return
		}
		_, _ = io.WriteString(conn, "HTTP/1.1 200 Connection Established\r\n\r\n")
		go func() { _, _ = io.Copy(upstream, conn); upstream.Close() }()
		_, _ = io.Copy(conn, upstream)
		conn.Close()
	}))
	defer proxy.Close()
	transport, err := newCloakTransport("chrome-latest", proxy.URL, UNKNOWN)
	if err != nil {
		t.Fatal(err)
	}
	defer transport.Close()
	client := &http.Client{Transport: transport, Timeout: 5 * time.Second}
	response, err := client.Get(origin.URL)
	if err != nil {
		t.Fatal(err)
	}
	body, err := io.ReadAll(response.Body)
	response.Body.Close()
	if err != nil || string(body) != "proxied" || connectCount.Load() != 1 {
		t.Fatalf("body=%q err=%v connects=%d", body, err, connectCount.Load())
	}
}

func TestCloakTransportRejectsUnsupportedConfiguration(t *testing.T) {
	for _, args := range [][3]string{{"missing-browser", "", ""}, {"chrome-latest", "ftp://localhost", ""}, {"chrome-latest", "", "http3"}} {
		transport, err := newCloakTransport(args[0], args[1], Proto(args[2]))
		if err == nil {
			transport.Close()
			t.Fatalf("accepted %v", args)
		}
	}
	ctx := context.WithValue(context.Background(), fastdialer.IP, "127.0.0.1")
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, "http://example.invalid", nil)
	_, err := testCloakClient(t, UNKNOWN).Do(req)
	if err == nil || !strings.Contains(err.Error(), "native-http") {
		t.Fatalf("custom IP accepted: %v", err)
	}
}
