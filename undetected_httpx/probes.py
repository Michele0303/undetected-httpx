import socket
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from undetected_httpx.manager import get_cdn_manager
from undetected_httpx.models import Response


def probe_status_code(response: Response) -> dict:
    return {"status_code": response.status_code}


def probe_content_length(response: Response) -> dict:
    cl = response.headers.get("content-length")
    if cl is None:
        cl = len(response.body)
    return {"content_length": cl}


def probe_content_type(response: Response) -> dict:
    ct = response.headers.get("content-type", "")
    ct_clean = ct.split(";")[0].strip()
    return {"content_type": ct_clean}


def probe_location(response: Response) -> dict:
    loc = response.headers.get("Location") or response.headers.get("location")
    if not loc and response.url != response.orig_url:
        loc = response.url
    return {"location": loc}


def probe_title(response: Response) -> dict:
    try:
        soup = BeautifulSoup(response.body, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else None
    except Exception:
        title = None

    return {"title": title or None}


def probe_response_time(response: Response) -> dict:
    return {"response_time": response.response_time}


def probe_ip(response: Response) -> dict:
    try:
        hostname = urlparse(response.url).hostname
        ip = socket.gethostbyname(hostname) if hostname else None
    except Exception:
        ip = None

    return {"ip": ip}


def probe_cdn(response: Response) -> dict:
    ip_data = probe_ip(response)
    ip = ip_data.get("ip")

    provider, category = get_cdn_manager().check(ip)
    return {"cdn": provider, "cdn_type": category}


PROBES = {
    "status_code": probe_status_code,
    "content_length": probe_content_length,
    "content_type": probe_content_type,
    "location": probe_location,
    "title": probe_title,
    "response_time": probe_response_time,
    "ip": probe_ip,
    "cdn": probe_cdn,
}


def run_probes(response: Response, enabled: dict) -> dict:
    result = {"url": response.url}

    for name, is_enabled in enabled.items():
        if is_enabled and name in PROBES:
            result.update(PROBES[name](response))

    return result
