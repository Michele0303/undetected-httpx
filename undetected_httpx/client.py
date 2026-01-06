from undetected_httpx.transport import Transport
from dataclasses import dataclass
import time


@dataclass
class Response:
    url: str
    orig_url: str
    status_code: int
    headers: dict
    body: bytes
    response_time: float


class Client:
    def __init__(
        self,
        timeout: int = 10,
        follow_redirects: bool = False,
        impersonate: str = "chrome",
    ):
        self.transport = Transport(
            timeout=timeout,
            follow_redirects=follow_redirects,
            impersonate=impersonate,
        )

    def get(self, url: str) -> Response:
        start = time.perf_counter()

        raw = self.transport.request("GET", url)

        elapsed = time.perf_counter() - start

        return Response(
            url=raw["url"],
            orig_url=url,
            status_code=raw["status_code"],
            headers=raw["headers"],
            body=raw["body"],
            response_time=elapsed * 1000,
        )
