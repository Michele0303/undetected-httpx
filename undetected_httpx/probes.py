import codecs
import hashlib
import socket
from urllib.parse import urlparse

import mmh3
from bs4 import BeautifulSoup
from jarm.scanner.scanner import Scanner

from undetected_httpx.manager import get_cdn_manager
from undetected_httpx.models import Response


class ProbeRunner:
    def __init__(self, client):
        self.client = client
        self._probes = {
            "status_code": self._status_code,
            "content_length": self._content_length,
            "content_type": self._content_type,
            "location": self._location,
            "title": self._title,
            "response_time": self._response_time,
            "ip": self._ip,
            "cdn": self._cdn,
            "favicon": self._favicon,
            "jarm": self._jarm,
        }

    def run(self, response: Response, enabled: dict) -> dict:
        result = {"url": response.url}
        for name, is_enabled in enabled.items():
            if is_enabled and name in self._probes:
                result.update(self._probes[name](response))

        if hash_algo := enabled.get("hash"):
            result["body_hash"] = self._hash(response, hash_algo)

        return result

    def _status_code(self, response: Response) -> dict:
        return {"status_code": response.status_code}

    def _content_length(self, response: Response) -> dict:
        cl = response.headers.get("content-length")
        if cl is None:
            cl = len(response.body)
        return {"content_length": cl}

    def _content_type(self, response: Response) -> dict:
        ct = response.headers.get("content-type", "")
        return {"content_type": ct.split(";")[0].strip()}

    def _location(self, response: Response) -> dict:
        loc = response.headers.get("Location") or response.headers.get("location")
        if not loc and response.url != response.orig_url:
            loc = response.url
        return {"location": loc}

    def _favicon(self, response: Response) -> dict:
        try:
            parsed = urlparse(response.url)
            favicon_url = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
            r = self.client.get(favicon_url)
            if r.status_code == 200 and r.body:
                favicon_b64 = codecs.encode(r.body, "base64")
                return {"favicon_hash": mmh3.hash(favicon_b64)}
        except Exception:
            pass
        return {"favicon_hash": None}

    def _hash(self, response: Response, algo: str) -> str | None:
        if not response.body:
            return None
        algo = algo.lower()
        if algo == "mmh3":
            return str(mmh3.hash(response.body))
        if algo in ("md5", "sha1", "sha256", "sha512"):
            return hashlib.new(algo, response.body).hexdigest()
        return None

    def _jarm(self, response: Response) -> dict:
        try:
            parsed = urlparse(response.url)
            hostname = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            jarm_hash, _, _ = Scanner.scan(hostname, port)
            return {"jarm": jarm_hash}
        except Exception:
            return {"jarm": None}

    def _title(self, response: Response) -> dict:
        try:
            soup = BeautifulSoup(response.body, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else None
        except Exception:
            title = None
        return {"title": title or None}

    def _response_time(self, response: Response) -> dict:
        return {"response_time": response.response_time}

    def _ip(self, response: Response) -> dict:
        try:
            hostname = urlparse(response.url).hostname
            ip = socket.gethostbyname(hostname) if hostname else None
        except Exception:
            ip = None
        return {"ip": ip}

    def _cdn(self, response: Response) -> dict:
        ip = self._ip(response).get("ip")
        provider, category = get_cdn_manager().check(ip)
        return {"cdn": provider, "cdn_type": category}
