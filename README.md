# undetected-httpx

<p align="center"> 
  <img src="https://img.shields.io/badge/python-3.14-blue.svg" alt="Python Version"> 
  <img src="https://img.shields.io/badge/impersonate-chrome%20|%20safari%20|%20firefox-green.svg" alt="Impersonation Support"> 
  <img src="https://img.shields.io/badge/license-MIT-red.svg" alt="License"> 
</p>

> **undetected-httpx** is a multi-purpose HTTP probing toolkit inspired by `httpx`. It is specifically engineered to bypass modern anti-bot infrastructures by mimicking real-world browser signatures.

Traditional HTTP clients are easily fingerprinted and blocked by WAFs. This tool leverages **browser-grade TLS** and **HTTP fingerprinting** (JA3/H2) to appear as a legitimate user, ensuring your reconnaissance stays under the radar.

-----

## 🎭 Real-world Comparison
*Can you spot the difference?* Standard tools get a `403 Forbidden` where we get a `200 OK`.

<table style="width: 100%; border-collapse: collapse; border: none;">
  <tr>
    <td align="center" style="border: none; width: 50%; padding: 10px;">
      <kbd><b>undetected-httpx (Pro)</b></kbd><br><br>
      <img src="https://raw.githubusercontent.com/michele0303/undetected-httpx/main/docs/undetected-httpx.gif" width="100%" style="border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
    </td>
    <td align="center" style="border: none; width: 50%; padding: 10px;">
      <kbd>httpx (Original)</kbd><br><br>
      <img src="https://raw.githubusercontent.com/michele0303/undetected-httpx/main/docs/httpx.gif" width="100%" style="border-radius: 8px; opacity: 0.8;">
    </td> 
  </tr>
</table>

-----

## 📊 Technical Capabilities

| Feature | `undetected-httpx` | `httpx` (Original) |
| :--- | :--- | :--- |
| **Network Stack** | `curl-impersonate` (C++) | Go `net/http` |
| **TLS Fingerprint** | ✅ **Identical** to Browsers | ❌ Easily Detected |
| **Cloudflare Bypass** | ✅ **Successful (200)** | ❌ Blocked (403) |
| **HTTP/2 Fingerprint** | ✅ Verified | ⚠️ Standard |

### 🛠 Key Features
- **Engine**: Powered by `curl_cffi` for high-performance impersonation.
- **Fingerprinting**: Full support for `JA3`, `JA4`, and `HTTP/2` settings randomization.
- **Seamless Transition**: Maintains CLI compatibility with ProjectDiscovery's `httpx` flags.
