import json
import time
import curl_cffi
import ipaddress
from pathlib import Path
from platformdirs import user_config_dir


class CDNManager:
    def __init__(self, cache_days=1):
        # cross-platform (Windows: AppData/Local, Linux: .config)
        self.cache_dir = Path(user_config_dir("undetected-httpx"))
        self.cache_file = self.cache_dir / "sources_data.json"
        self.url = "https://raw.githubusercontent.com/projectdiscovery/cdncheck/main/sources_data.json"
        self.cache_seconds = cache_days * 24 * 60 * 60

        self.data = {}
        self._lookup_cache = {}  # in-memory cache for quick lookups

        self._initialize_data()

    def _initialize_data(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if (
            not self.cache_file.exists()
            or (time.time() - self.cache_file.stat().st_mtime) > self.cache_seconds
        ):
            self._update_cache()
        else:
            self._load_from_disk()

    def _update_cache(self):
        try:
            response = curl_cffi.get(self.url, timeout=15)
            if response.status_code == 200:
                self.data = response.json()
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False)
            elif self.cache_file.exists():
                self._load_from_disk()
        except Exception:
            if self.cache_file.exists():
                self._load_from_disk()

    def _load_from_disk(self):
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}

    def check(self, ip_str):
        if not ip_str or not self.data:
            return None, None

        # check cache first
        if ip_str in self._lookup_cache:
            return self._lookup_cache[ip_str]

        try:
            ip_obj = ipaddress.ip_address(ip_str)
            for category in ["waf", "cdn", "cloud"]:
                for provider, cidrs in self.data.get(category, {}).items():
                    for cidr in cidrs:
                        if ip_obj in ipaddress.ip_network(cidr):
                            res = (provider, category)
                            self._lookup_cache[ip_str] = res
                            return res
        except Exception:
            pass

        self._lookup_cache[ip_str] = (None, None)
        return None, None
