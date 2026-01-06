from curl_cffi.requests import Session


class Transport:
    def __init__(
        self,
        impersonate: str,
        timeout: int = 10,
        proxy: str | None = None,
        follow_redirects: bool = False,
    ):
        self.follow_redirects = follow_redirects
        self.session = Session(
            impersonate=impersonate,
            proxy=proxy,
            timeout=timeout,
        )

    def request(self, method: str, url: str) -> dict:
        r = self.session.request(
            method,
            url,
            allow_redirects=self.follow_redirects,
        )

        return {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body": r.content,
            "url": str(r.url),
            "orig_url": url,
        }

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
