import typer
from pathlib import Path
from typing import List, Optional
import sys

from undetected_httpx.client import Client
from undetected_httpx.probes import run_probes
from undetected_httpx.output import render_stdout, render_json

app = typer.Typer(
    add_completion=False,
    help="An HTTP probing toolkit inspired by httpx, powered by curl_cffi.",
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "-help", "--help"]},
)


@app.command()
def scan(
    # INPUT
    list_file: Optional[Path] = typer.Option(
        None,
        "-l",
        "-list",
        help="input file containing list of hosts to process",
        rich_help_panel="INPUT",
    ),
    target: Optional[List[str]] = typer.Option(
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
    title: bool = typer.Option(
        False, "-title", help="Display page title", rich_help_panel="PROBES"
    ),
    response_time: bool = typer.Option(
        False,
        "-rt",
        "-response-time",
        help="Display response time",
        rich_help_panel="PROBES",
    ),
    # CONFIG
    timeout: int = typer.Option(
        10,
        "-timeout",
        help="timeout in seconds (default 10)",
        rich_help_panel="CONFIGURATIONS",
    ),
    impersonate: str = typer.Option(
        "chrome",
        "--impersonate",
        help="Browser fingerprint to impersonate",
        rich_help_panel="CONFIGURATIONS",
    ),
    # OUTPUT
    json: bool = typer.Option(
        False,
        "-j",
        "-json",
        help="store output in JSONL(ines) format",
        rich_help_panel="OUTPUT",
    ),
):
    targets: List[str] = []

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

    client = Client(
        timeout=timeout,
        impersonate=impersonate,
    )

    enabled_probes = {
        "status_code": status_code,
        "title": title,
        "response_time": response_time,
    }

    for t in targets:
        try:
            response = client.get(t)
            result = run_probes(response, enabled_probes)

            if json:
                render_json(result)
            else:
                render_stdout(result)
        except Exception as e:
            typer.secho(f"Error connecting to {t}: {e}", fg="red", err=True)


def main():
    app()


if __name__ == "__main__":
    main()
