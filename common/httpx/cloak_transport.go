package httpx

import (
	"bufio"
	"compress/flate"
	"compress/gzip"
	"compress/zlib"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"

	"github.com/andybalholm/brotli"
	"github.com/klauspost/compress/zstd"
	"github.com/projectdiscovery/fastdialer/fastdialer"
	cloakhttp "github.com/sardanioss/http"
	"github.com/sardanioss/httpcloak/dns"
	"github.com/sardanioss/httpcloak/fingerprint"
	cloak "github.com/sardanioss/httpcloak/transport"
)

// cloakTransport keeps net/http's redirect and cookie handling while delegating
// each exchange to httpcloak. Response decompression streams through HTTPX's
// size limit, without buffering the full body inside httpcloak.
type cloakTransport struct {
	preset   *fingerprint.Preset
	protocol Proto
	proxy    func(*http.Request) (*url.URL, error)
	mu       sync.Mutex
	routes   map[string]*cloakRoute
	closed   bool
}

type cloakRoute struct {
	h1 *cloak.HTTP1Transport
	h2 *cloak.HTTP2Transport
}

var _ http.RoundTripper = (*cloakTransport)(nil)

func newCloakTransport(presetName, proxyURL string, protocol Proto) (*cloakTransport, error) {
	if presetName == "" {
		presetName = "chrome-latest"
	}
	preset := fingerprint.GetStrict(presetName)
	if preset == nil {
		return nil, fmt.Errorf("unknown httpcloak browser preset %q; available: %s", presetName, strings.Join(fingerprint.KnownPresets(), ", "))
	}
	if protocol != UNKNOWN && protocol != HTTP11 && protocol != HTTP2 {
		return nil, fmt.Errorf("httpcloak supports http11 and http2; got %q", protocol)
	}
	if protocol == HTTP2 && preset.DisableHTTP2 {
		return nil, fmt.Errorf("httpcloak browser preset %q disables HTTP/2", presetName)
	}
	t := &cloakTransport{preset: preset, protocol: protocol, proxy: http.ProxyFromEnvironment, routes: make(map[string]*cloakRoute)}
	if proxyURL != "" {
		u, err := parseCloakProxy(proxyURL)
		if err != nil {
			return nil, err
		}
		t.proxy = http.ProxyURL(u)
	}
	return t, nil
}

func parseCloakProxy(raw string) (*url.URL, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return nil, fmt.Errorf("invalid httpcloak proxy URL")
	}
	switch u.Scheme {
	case "http", "https", "socks5", "socks5h":
	default:
		return nil, fmt.Errorf("httpcloak proxy requires http, https, socks5, or socks5h")
	}
	if u.Hostname() == "" {
		return nil, fmt.Errorf("httpcloak proxy URL requires a host")
	}
	return u, nil
}

func (t *cloakTransport) route(req *http.Request) (*cloakRoute, error) {
	proxyURL, err := t.proxy(req)
	if err != nil {
		return nil, err
	}
	key := ""
	var proxy *cloak.ProxyConfig
	if proxyURL != nil {
		if _, err := parseCloakProxy(proxyURL.String()); err != nil {
			return nil, err
		}
		key = proxyURL.String()
		proxy = &cloak.ProxyConfig{URL: key}
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.closed {
		return nil, errors.New("httpcloak transport is closed")
	}
	if r := t.routes[key]; r != nil {
		return r, nil
	}
	cache := dns.NewCache()
	r := &cloakRoute{
		h1: cloak.NewHTTP1TransportWithProxy(t.preset, cache, proxy),
		h2: cloak.NewHTTP2TransportWithProxy(t.preset, cache, proxy),
	}
	// HTTPX probes endpoints with expired and self-signed certificates too.
	r.h1.SetInsecureSkipVerify(true)
	r.h2.SetInsecureSkipVerify(true)
	t.routes[key] = r
	return r, nil
}

func (t *cloakTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if req == nil || req.URL == nil {
		return nil, errors.New("httpcloak requires a request URL")
	}
	if req.Context().Value(fastdialer.IP) != nil {
		closeCloakRequest(req)
		return nil, errors.New("custom IP dialing requires --native-http")
	}
	if req.URL.Scheme != "http" && req.URL.Scheme != "https" {
		closeCloakRequest(req)
		return nil, fmt.Errorf("unsupported URL scheme %q", req.URL.Scheme)
	}
	if t.protocol == HTTP2 && req.URL.Scheme != "https" {
		closeCloakRequest(req)
		return nil, errors.New("httpcloak http2 requires HTTPS; cleartext HTTP/2 is unsupported")
	}
	route, err := t.route(req)
	if err != nil {
		closeCloakRequest(req)
		return nil, err
	}
	ctx, cancel := context.WithCancel(req.Context())
	fork, err := cloakhttp.NewRequestWithContext(ctx, req.Method, req.URL.String(), req.Body)
	if err != nil {
		cancel()
		closeCloakRequest(req)
		return nil, err
	}
	fork.Host = req.Host
	fork.ContentLength = req.ContentLength
	fork.GetBody = req.GetBody
	fork.Close = req.Close
	fork.Trailer = cloakhttp.Header(req.Trailer.Clone())
	fork.TransferEncoding = append([]string(nil), req.TransferEncoding...)
	if req.Body == http.NoBody {
		fork.Body = cloakhttp.NoBody
	}
	useH1 := req.URL.Scheme == "http" || t.protocol == HTTP11 || t.preset.DisableHTTP2
	t.applyHeaders(fork, req.Header, useH1)
	var response *cloakhttp.Response
	if useH1 {
		response, err = route.h1.RoundTrip(fork)
	} else {
		response, err = route.h2.RoundTrip(fork)
		var mismatch *cloak.ALPNMismatchError
		if errors.As(err, &mismatch) {
			if t.protocol != HTTP2 && (mismatch.Negotiated == "http/1.1" || mismatch.Negotiated == "") {
				t.applyHeaders(fork, req.Header, true)
				response, err = route.h1.RoundTripWithTLSConn(fork, mismatch.TLSConn, mismatch.Host, mismatch.Port)
			} else if mismatch.TLSConn != nil {
				_ = mismatch.TLSConn.Close()
			}
		}
	}
	if err != nil {
		cancel()
		closeCloakRequest(req)
		if response != nil && response.Body != nil {
			_ = response.Body.Close()
		}
		return nil, err
	}
	body := &cloakBody{ReadCloser: response.Body, cancel: cancel}
	decoded := false
	if req.Method != http.MethodHead && response.ContentLength != 0 && response.StatusCode != http.StatusNoContent && response.StatusCode != http.StatusNotModified && response.StatusCode >= 200 {
		decoded, err = body.decode(response.Header.Get("Content-Encoding"))
	}
	if err != nil {
		_ = body.Close()
		return nil, fmt.Errorf("httpcloak response decompression: %w", err)
	}
	result := &http.Response{
		Status: response.Status, StatusCode: response.StatusCode,
		Proto: response.Proto, ProtoMajor: response.ProtoMajor, ProtoMinor: response.ProtoMinor,
		Header:        cleanCloakHeaders(response.Header),
		Body:          body,
		ContentLength: response.ContentLength, TransferEncoding: response.TransferEncoding,
		Close: response.Close, Uncompressed: response.Uncompressed,
		Trailer: http.Header(response.Trailer), Request: req,
	}
	if decoded {
		result.Header.Del("Content-Encoding")
		result.Header.Del("Content-Length")
		result.ContentLength = -1
		result.Uncompressed = true
	}
	if response.TLS != nil {
		state := cloak.ToStdConnectionState(*response.TLS)
		result.TLS = &state
	}
	return result, nil
}

func (t *cloakTransport) applyHeaders(req *cloakhttp.Request, headers http.Header, h1 bool) {
	req.Header = make(cloakhttp.Header)
	for _, pair := range t.preset.HeaderOrder {
		req.Header.Set(pair.Key, pair.Value)
	}
	for key, value := range t.preset.Headers {
		if _, exists := req.Header[http.CanonicalHeaderKey(key)]; !exists {
			req.Header.Set(key, value)
		}
	}
	req.Header.Set("User-Agent", t.preset.UserAgent)
	if h1 && !t.preset.SendsPriorityOverHTTP1() {
		req.Header.Del("Priority")
	}
	for key, values := range headers {
		req.Header[http.CanonicalHeaderKey(key)] = append([]string(nil), values...)
	}
	req.Header[cloakhttp.HeaderOrderKey] = cloak.CompleteHeaderOrder(nil, t.preset.H2HeaderOrderFor(req.Header.Get("Sec-Fetch-Dest")), req.Header, headers)
	req.Header[cloakhttp.PHeaderOrderKey] = t.preset.H2PseudoHeaderOrder()
}

func cleanCloakHeaders(header cloakhttp.Header) http.Header {
	result := make(http.Header, len(header))
	for key, values := range header {
		// httpcloak stores wire-order metadata under names containing a colon.
		if !strings.Contains(key, ":") {
			result[http.CanonicalHeaderKey(key)] = append([]string(nil), values...)
		}
	}
	return result
}

func closeCloakRequest(req *http.Request) {
	if req.Body != nil {
		_ = req.Body.Close()
	}
}

// Cancel before closing an unread H1 body: its Close otherwise drains the
// entire response, defeating the scanner's response size limit.
type cloakBody struct {
	io.ReadCloser
	cancel       context.CancelFunc
	reader       io.Reader
	closeDecoder func()
}

func (b *cloakBody) decode(encoding string) (bool, error) {
	switch strings.ToLower(strings.TrimSpace(encoding)) {
	case "gzip", "x-gzip":
		reader, err := gzip.NewReader(b.ReadCloser)
		if err != nil {
			return false, err
		}
		b.reader = reader
		b.closeDecoder = func() { _ = reader.Close() }
	case "deflate":
		buffered := bufio.NewReader(b.ReadCloser)
		header, err := buffered.Peek(2)
		if err != nil {
			return false, err
		}
		var reader io.ReadCloser
		if header[0]&0x0f == 8 && (int(header[0])<<8|int(header[1]))%31 == 0 {
			reader, err = zlib.NewReader(buffered)
		} else {
			reader = flate.NewReader(buffered)
		}
		if err != nil {
			return false, err
		}
		b.reader = reader
		b.closeDecoder = func() { _ = reader.Close() }
	case "br":
		b.reader = brotli.NewReader(b.ReadCloser)
	case "zstd":
		reader, err := zstd.NewReader(b.ReadCloser, zstd.WithDecoderConcurrency(1), zstd.WithDecoderMaxMemory(64<<20))
		if err != nil {
			return false, err
		}
		b.reader = reader
		b.closeDecoder = reader.Close
	default:
		return false, nil
	}
	return true, nil
}

func (b *cloakBody) Read(p []byte) (int, error) {
	if b.reader != nil {
		return b.reader.Read(p)
	}
	return b.ReadCloser.Read(p)
}

func (b *cloakBody) Close() error {
	b.cancel()
	err := b.ReadCloser.Close()
	if b.closeDecoder != nil {
		b.closeDecoder()
	}
	return err
}

func (t *cloakTransport) CloseIdleConnections() {
	t.mu.Lock()
	routes := t.routes
	t.routes = make(map[string]*cloakRoute)
	t.mu.Unlock()
	for _, r := range routes {
		r.h1.Close()
		r.h2.CloseGraceful()
	}
}

func (t *cloakTransport) Close() {
	t.mu.Lock()
	t.closed = true
	routes := t.routes
	t.routes = make(map[string]*cloakRoute)
	t.mu.Unlock()
	for _, r := range routes {
		r.h1.Close()
		r.h2.Close()
	}
}
