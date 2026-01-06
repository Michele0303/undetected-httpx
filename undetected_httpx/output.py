import json
import typer


def render_stdout(result: dict, silent: bool = False):
    if silent:
        print(result.get("url", ""))
        return

    url = result.get("url", "")

    status_part = ""
    if "status_code" in result and result["status_code"]:
        sc = result["status_code"]
        color = "green" if 200 <= sc < 300 else "yellow" if 300 <= sc < 400 else "red"
        status_text = typer.style(f"{sc}", fg=color, bold=True)
        status_part = f" [{status_text}]"

    content_length_part = ""
    if "content_length" in result and result["content_length"]:
        cl = result["content_length"]
        content_length_text = typer.style(f"{cl}", fg="magenta")
        content_length_part = f" [{content_length_text}]"

    content_type_part = ""
    if "content_type" in result and result["content_type"]:
        ct = result["content_type"]
        content_type_text = typer.style(f"{ct}", fg="magenta")
        content_type_part = f" [{content_type_text}]"

    location_part = ""
    if "location" in result and result["location"]:
        location_text = typer.style(result["location"], fg="magenta")
        location_part = f" [{location_text}]"

    title_part = ""
    if "title" in result and result["title"]:
        title_text = typer.style(result["title"], fg="cyan")
        title_part = f" [{title_text}]"

    response_time_part = ""
    if "response_time" in result and result["response_time"]:
        rt = result["response_time"]
        response_time_text = typer.style(f"{rt:.2f}ms", fg="magenta")
        response_time_part = f" [{response_time_text}]"

    ip_part = ""
    if "ip" in result and result["ip"]:
        ip_text = typer.style(result["ip"], fg="magenta")
        ip_part = f" [{ip_text}]"

    print(
        f"{url}{status_part}{location_part}{content_length_part}{content_type_part}{title_part}{ip_part}{response_time_part}"
    )


def render_json(result: dict):
    print(json.dumps(result, ensure_ascii=False))
