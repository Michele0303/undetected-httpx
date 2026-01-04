from curl_cffi import requests


class Transport:
    def __init__(
        self,
        impersonate: str,
        timeout: int = 10,
        proxy: str = None,
        follow_redirects: bool = False,
    ):
        self.impersonate = impersonate
        self.timeout = timeout
        self.proxy = proxy
        self.follow_redirects = follow_redirects

    def request(self, method: str, url: str) -> dict:
        r = requests.request(
            method,
            url,
            impersonate=self.impersonate,
            proxy=self.proxy,
            timeout=self.timeout,
            allow_redirects=self.follow_redirects,
        )

        return {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body": r.content,
            "url": r.url,
            "orig_url": url,
        }
