import json
import typer


def _styled_part(value, color: str | None = None, bold: bool = False) -> str:
    if not value:
        return ""
    styled = typer.style(str(value), fg=color, bold=bold)
    return f" [{styled}]"


def render_stdout(result: dict, silent: bool = False) -> None:
    if silent:
        print(result.get("url", ""))
        return

    url = result.get("url", "")

    status_part = ""
    if sc := result.get("status_code"):
        color = "green" if 200 <= sc < 300 else "yellow" if 300 <= sc < 400 else "red"
        status_part = _styled_part(sc, color, bold=True)

    content_length_part = _styled_part(result.get("content_length"), "magenta")
    content_type_part = _styled_part(result.get("content_type"), "magenta")
    location_part = _styled_part(result.get("location"), "magenta")
    title_part = _styled_part(result.get("title"), "cyan")
    ip_part = _styled_part(result.get("ip"))
    cdn_part = _styled_part(result.get("cdn"))

    rt = result.get("response_time")
    response_time_part = _styled_part(f"{rt:.2f}ms" if rt else None)

    print(
        f"{url}{status_part}{location_part}{content_length_part}"
        f"{content_type_part}{title_part}{ip_part}{cdn_part}"
        f"{response_time_part}"
    )


def render_json(result: dict) -> None:
    print(json.dumps(result, ensure_ascii=False))
