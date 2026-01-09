from dataclasses import dataclass


@dataclass
class Response:
    url: str
    orig_url: str
    status_code: int
    headers: dict
    body: bytes
    response_time: float
