import json
import typer


def _styled_part(
    value, color: str | None = None, bold: bool = False, show_empty: bool = False
) -> str:
    if not value:
        return " []" if show_empty else ""
    styled = typer.style(str(value), fg=color, bold=bold)
    return f" [{styled}]"


def render_stdout(result: dict, silent: bool = False) -> None:
    if silent:
        print(result.get("url", ""))
        return

    url = result.get("url", "")

    status_part = ""
    if "status_code" in result:
        sc = result["status_code"]
        if sc:
            color = (
                "green" if 200 <= sc < 300 else "yellow" if 300 <= sc < 400 else "red"
            )
            status_part = _styled_part(sc, color, bold=True)
        else:
            status_part = " []"

    location_part = _styled_part(
        result.get("location"), "magenta", show_empty=("location" in result)
    )
    content_length_part = _styled_part(
        result.get("content_length"), "magenta", show_empty=("content_length" in result)
    )
    content_type_part = _styled_part(
        result.get("content_type"), "magenta", show_empty=("content_type" in result)
    )
    title_part = _styled_part(
        result.get("title"), "cyan", show_empty=("title" in result)
    )
    ip_part = _styled_part(result.get("ip"), show_empty=("ip" in result))
    cdn_part = _styled_part(result.get("cdn"), show_empty=("cdn" in result))

    response_time_part = ""
    if "response_time" in result:
        rt = result["response_time"]
        response_time_part = _styled_part(
            f"{rt:.2f}ms" if rt else None, show_empty=True
        )

    favicon_part = _styled_part(
        result.get("favicon_hash"), show_empty=("favicon_hash" in result)
    )

    print(
        f"{url}{status_part}{location_part}{content_length_part}"
        f"{content_type_part}{title_part}{ip_part}{cdn_part}"
        f"{response_time_part}{favicon_part}"
    )


def render_json(result: dict) -> None:
    print(json.dumps(result, ensure_ascii=False))
