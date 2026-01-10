import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from undetected_httpx import __version__
from undetected_httpx.client import Client
from undetected_httpx.probes import ProbeRunner
from undetected_httpx.output import render_stdout, render_json

app = typer.Typer(
    add_completion=False,
    help="An HTTP probing toolkit inspired by httpx, powered by curl_cffi.",
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "-help", "--help"]},
)

console = Console()


def show_banner() -> None:
    ascii_art = r"""
░█░█░█▀█░█▀▄░█▀▀░▀█▀░█▀▀░█▀▀░▀█▀░█▀▀░█▀▄░░░█░█░▀█▀░▀█▀░█▀█░█░█
░█░█░█░█░█░█░█▀▀░░█░░█▀▀░█░░░░█░░█▀▀░█░█░░░█▀█░░█░░░█░░█▀▀░▄▀▄
░▀▀▀░▀░▀░▀▀░░▀▀▀░░▀░░▀▀▀░▀▀▀░░▀░░▀▀▀░▀▀░░░░▀░▀░░▀░░░▀░░▀░░░▀░▀
    """

    console.print(
        Panel(
            f"[bold yellow]{ascii_art}[/bold yellow]\n"
            f"[bold cyan]Undetected HTTPX Toolkit[/bold cyan] | [dim]v{__version__}[/dim]",
            border_style="yellow",
            expand=False,
        )
    )


@app.command()
def scan(
    # INPUT
    list_file: Path | None = typer.Option(
        None,
        "-l",
        "-list",
        help="input file containing list of hosts to process",
        rich_help_panel="INPUT",
    ),
    target: list[str] | None = typer.Option(
        None,
        "-u",
        "-target",
        help="input target host(s) to probe",
        rich_help_panel="INPUT",
    ),
    # PROBES
    status_code: bool = typer.Option(
        False,
        "-sc",
        "-status-code",
        help="Display status code",
        rich_help_panel="PROBES",
    ),
    content_length: bool = typer.Option(
        False,
        "-cl",
        "-content-length",
        help="display response content-length",
        rich_help_panel="PROBES",
    ),
    content_type: bool = typer.Option(
        False,
        "-ct",
        "-content-type",
        help="display response content-type",
        rich_help_panel="PROBES",
    ),
    location: bool = typer.Option(
        False,
        "-location",
        help="display response redirect location",
        rich_help_panel="PROBES",
    ),
    favicon: bool = typer.Option(
        False,
        "-favicon",
        help="display mmh3 hash for '/favicon.ico' file",
        rich_help_panel="PROBES",
    ),
    title: bool = typer.Option(
        False,
        "-title",
        help="display response content-length",
        rich_help_panel="PROBES",
    ),
    response_time: bool = typer.Option(
        False,
        "-rt",
        "-response-time",
        help="display response time",
        rich_help_panel="PROBES",
    ),
    ip: bool = typer.Option(
        False,
        "-ip",
        help="display host ip",
        rich_help_panel="PROBES",
    ),
    cdn: bool = typer.Option(
        False,
        "-cdn",
        help="display cdn/waf in use",
        rich_help_panel="PROBES",
    ),
    # RATE-LIMIT
    threads: int = typer.Option(
        50,
        "-t",
        "-threads",
        help="number of threads to use (default 50)",
        rich_help_panel="RATE-LIMIT",
    ),
    # OUTPUT
    json: bool = typer.Option(
        False,
        "-j",
        "-json",
        help="store output in JSONL(ines) format",
        rich_help_panel="OUTPUT",
    ),
    silent: bool = typer.Option(
        False, "-silent", help="silent mode", rich_help_panel="DEBUG"
    ),
    # CONFIGURATIONS
    fhr: bool = typer.Option(
        False,
        "-fhr",
        "-follow-host-redirects",
        help="follow redirects on the same host",
        rich_help_panel="CONFIGURATIONS",
    ),
    impersonate: str = typer.Option(
        "chrome",
        "-impersonate",
        help="Browser fingerprint to impersonate",
        rich_help_panel="CONFIGURATIONS",
    ),
    # OPTIMIZATIONS
    timeout: int = typer.Option(
        10,
        "-timeout",
        help="timeout in seconds (default 10)",
        rich_help_panel="OPTIMIZATIONS",
    ),
) -> None:
    if not silent:
        show_banner()

    targets: list[str] = []

    if list_file:
        if list_file.is_file():
            targets.extend(t.strip() for t in list_file.read_text().splitlines() if t)
        else:
            typer.secho(f"Error: {list_file} is not a valid file.", fg="red", err=True)
            raise typer.Exit(1)

    if target:
        targets.extend(target)

    # stdin
    if not targets and not sys.stdin.isatty():
        targets.extend(t.strip() for t in sys.stdin.read().splitlines() if t)

    if not targets:
        typer.secho(
            "No targets provided. Use -u, -l or pipe from stdin.", fg="yellow", err=True
        )
        raise typer.Exit(1)

    enabled_probes = {
        "status_code": status_code,
        "content_length": content_length,
        "content_type": content_type,
        "location": location,
        "favicon": favicon,
        "title": title,
        "response_time": response_time,
        "ip": ip,
        "cdn": cdn,
    }

    print_lock = threading.Lock()

    def process_target(url: str) -> None:
        try:
            with Client(
                timeout=timeout, impersonate=impersonate, follow_redirects=fhr
            ) as client:
                response = client.get(url)
                result = ProbeRunner(client).run(response, enabled_probes)

            with print_lock:
                render_json(result) if json else render_stdout(result)

        except Exception as e:
            with print_lock:
                typer.secho(f"Error: {url}: {e}", fg="red", err=True)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        list(executor.map(process_target, targets))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
