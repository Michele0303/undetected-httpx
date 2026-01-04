from undetected_httpx.transport import Transport
from dataclasses import dataclass
import time


@dataclass
class Response:
    url: str
    status_code: int
    headers: dict
    body: bytes
    elapsed: float


class Client:
    def __init__(self, timeout=10, impersonate="chrome"):
        self.transport = Transport(
            timeout=timeout,
            impersonate=impersonate,
        )

    def get(self, url: str) -> Response:
        start = time.time()
        raw = self.transport.request("GET", url)
        elapsed = time.time() - start

        return Response(
            url=url,
            status_code=raw["status_code"],
            headers=raw["headers"],
            body=raw["body"],
            elapsed=elapsed,
        )
