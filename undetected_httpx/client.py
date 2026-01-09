import time
from curl_cffi.requests import Session

from undetected_httpx.models import Response


class Client:
    def __init__(
        self,
        timeout: int = 10,
        follow_redirects: bool = False,
        impersonate: str = "chrome",
        proxy: str | None = None,
    ):
        self.follow_redirects = follow_redirects
        self._session = Session(
            impersonate=impersonate,
            proxy=proxy,
            timeout=timeout,
        )

    def get(self, url: str) -> Response:
        start = time.perf_counter()
        r = self._session.request("GET", url, allow_redirects=self.follow_redirects)
        elapsed = (time.perf_counter() - start) * 1000

        return Response(
            url=str(r.url),
            orig_url=url,
            status_code=r.status_code,
            headers=dict(r.headers),
            body=r.content,
            response_time=elapsed,
        )

    def close(self):
        self._session.close()
