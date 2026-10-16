import json
import time
import ipaddress
from functools import lru_cache
from pathlib import Path

import curl_cffi
from platformdirs import user_config_dir


@lru_cache(maxsize=1)
def get_cdn_manager() -> "CDNManager":
    return CDNManager()


class CDNManager:
    CACHE_URL = "https://raw.githubusercontent.com/projectdiscovery/cdncheck/main/sources_data.json"

    def __init__(self, cache_days: int = 1):
        self.cache_file = (
            Path(user_config_dir("undetected-httpx")) / "sources_data.json"
        )
        self.cache_seconds = cache_days * 86400
        self._networks = []
        self._lookup_cache = {}
        self._load_data()

    def _load_data(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.cache_file.exists() or self._cache_expired():
            self._fetch_remote()

        try:
            data = json.loads(self.cache_file.read_text())
            self._build_network_list(data)
        except (json.JSONDecodeError, OSError):
            self._networks = []

    def _cache_expired(self) -> bool:
        return time.time() - self.cache_file.stat().st_mtime > self.cache_seconds

    def _fetch_remote(self) -> None:
        try:
            r = curl_cffi.get(self.CACHE_URL, timeout=15)
            if r.status_code == 200:
                self.cache_file.write_text(r.text)
        except Exception:
            pass

    def _build_network_list(self, data: dict) -> None:
        for category in ("waf", "cdn", "cloud"):
            for provider, cidrs in data.get(category, {}).items():
                for cidr in cidrs:
                    try:
                        net = ipaddress.ip_network(cidr, strict=False)
                        self._networks.append((net, provider, category))
                    except ValueError:
                        continue

    def check(self, ip_str: str) -> tuple[str | None, str | None]:
        if not ip_str or not self._networks:
            return None, None

        if ip_str in self._lookup_cache:
            return self._lookup_cache[ip_str]

        try:
            ip = ipaddress.ip_address(ip_str)
            for net, provider, category in self._networks:
                if ip in net:
                    self._lookup_cache[ip_str] = (provider, category)
                    return provider, category
        except ValueError:
            pass

        self._lookup_cache[ip_str] = (None, None)
        return None, None
