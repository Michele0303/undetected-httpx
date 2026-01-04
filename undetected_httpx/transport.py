from curl_cffi import requests


class Transport:
    def __init__(self, impersonate: str, timeout: int = 10, proxy: str = None):
        self.impersonate = impersonate
        self.proxy = proxy
        self.timeout = timeout

    def request(self, method: str, url: str) -> dict:
        r = requests.request(
            method,
            url,
            impersonate=self.impersonate,
            proxy=self.proxy,
            timeout=self.timeout,
            allow_redirects=True,
        )

        return {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body": r.content,
        }
