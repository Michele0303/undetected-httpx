from undetected_httpx.client import Response
from bs4 import BeautifulSoup


def probe_status_code(response: Response) -> dict:
    return {"status_code": response.status_code}


def probe_title(response: Response) -> dict:
    try:
        soup = BeautifulSoup(response.body, "html.parser")
        title = soup.title.string.strip() if soup.title else ""
    except Exception:
        title = ""

    return {"title": title}


PROBES = {
    "status_code": probe_status_code,
    "title": probe_title,
}


def run_probes(response: Response, enabled: dict) -> dict:
    result = {"url": response.url}

    for name, is_enabled in enabled.items():
        if is_enabled and name in PROBES:
            result.update(PROBES[name](response))

    return result
