from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.status import Status
from rich.table import Table
from rich.text import Text

_console = Console(stderr=True)
_log_json: bool = False

StepCallback = Callable[[int, int | None, str], None]


def set_mode(log_json: bool) -> None:
    global _log_json
    _log_json = log_json


def _strip_markup(text: str) -> str:
    return Text.from_markup(text).plain


def _emit(event: str, data: Any = None, **extra: Any) -> None:
    record: dict[str, Any] = {"event": _strip_markup(event)}
    if data is not None:
        record["data"] = data
    record.update(extra)
    _console.print_json(data=record)


def message(text: str, style: str = "", data: Any = None) -> None:
    if _log_json:
        _emit(text, data)
    else:
        _console.print(text, style=style) if style else _console.print(text)


def ok(text: str, data: Any = None) -> None:
    if _log_json:
        _emit(f"ok | {text}", data=data)
    else:
        _console.print(f"  [bold green]●[/] {text}")


def fail(text: str, data: Any = None) -> None:
    if _log_json:
        _emit(f"fail | {text}", data=data)
    else:
        _console.print(f"  [bold red]●[/] {text}")


def warn(text: str, data: Any = None) -> None:
    if _log_json:
        _emit(f"warn | {text}", data=data)
    else:
        _console.print(f"  [bold yellow]●[/] {text}")


def info(text: str, data: Any = None) -> None:
    if _log_json:
        _emit(f"info | {text}", data=data)
    else:
        _console.print(f"  [cyan]●[/] {text}")


def panel(title: str, content: str, style: str = "green", data: Any = None) -> None:
    if _log_json:
        _emit(title, data)
    else:
        _console.print(Panel(Text(content), title=title, border_style=style))


def table(title: str, columns: list[str], rows: list[list[Any]], data: Any = None) -> None:
    if _log_json:
        _emit(title, data)
    else:
        t = Table(title=title, title_style="bold", border_style="dim")
        for col in columns:
            t.add_column(col)
        for row in rows:
            t.add_row(*[str(c) for c in row])
        _console.print(t)


def progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=_console,
        transient=False,
    )


def spinner(description: str) -> Status:
    return Status(description, console=_console, spinner="dots")


def install_traceback() -> None:
    from rich.traceback import install as _install

    _install(show_locals=False, console=_console)
