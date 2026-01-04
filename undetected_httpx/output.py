import json
import typer


def render_stdout(result: dict, silent: bool = False):
    if silent:
        print(result.get("url", ""))
        return

    url = result.get("url", "")

    status_part = ""
    if "status_code" in result:
        sc = result["status_code"]
        color = "green" if 200 <= sc < 300 else "yellow" if 300 <= sc < 400 else "red"
        status_text = typer.style(f"{sc}", fg=color, bold=True)
        status_part = f" [{status_text}]"

    title_part = ""
    if "title" in result and result["title"]:
        title_text = typer.style(result["title"], fg="cyan")
        title_part = f" [{title_text}]"

    print(f"{url}{status_part}{title_part}")


def render_json(result: dict):
    print(json.dumps(result, ensure_ascii=False))
