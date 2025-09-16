import atexit
import logging
from pathlib import Path

import click
import urllib3
from rich import traceback
from rich.console import Group
from rich.padding import Padding
from rich.text import Text
from urllib3.exceptions import InsecureRequestWarning

from vindemitor.core import __version__
from vindemitor.core.commands import Commands
from vindemitor.core.config import config
from vindemitor.core.console import ComfyRichHandler, console
from vindemitor.core.constants import context_settings
from vindemitor.core.utilities import rotate_log_file

LOGGING_PATH = None


@click.command(cls=Commands, invoke_without_command=True, context_settings=context_settings)
@click.option("-v", "--version", is_flag=True, default=False, help="Print version information.")
@click.option("-d", "--debug", is_flag=True, default=False, help="Enable DEBUG level logs.")
@click.option(
    "--log",
    "log_path",
    type=Path,
    default=config.paths.directories.logs / config.paths.filenames.log,
    help="Log path (or filename). Path can contain the following f-string args: {name} {time}.",
)
def main(version: bool, debug: bool, log_path: Path) -> None:
    """vindemitor—Modular Movie, TV, and Music Archival Software."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(message)s",
        handlers=[
            ComfyRichHandler(
                show_time=False,
                show_path=debug,
                console=console,
                rich_tracebacks=True,
                tracebacks_suppress=[click],
                log_renderer=console._log_render,  # noqa
            )
        ],
    )

    if log_path:
        global LOGGING_PATH
        console.record = True
        new_log_path = rotate_log_file(log_path)
        LOGGING_PATH = new_log_path

    urllib3.disable_warnings(InsecureRequestWarning)

    traceback.install(console=console, width=80, suppress=[click])

    console.print(
        Padding(
            Group(
                Text(
                    r" .          ⠀⠀⠀✦             ˚       ♍︎" + "\n"
                    r"   . ✦     ˚     .  ⋆.     ★    . ˚.   " + "\n"
                    r" ✦   .  .   ✦ ˚        .˚     ✦        " + "\n"
                    r"...- .. -. -.. . -- .. .- - .-. .. -..-",
                    style="ascii.art",
                ),
            ),
            (1, 21, 1, 20),
            expand=True,
        ),
        Padding(
            Group(
                f"v[repr.number]{__version__}[/] Copyright © 2025 Shivelight",
                "v[rgb(166,173,200)]3.3.3[/] Copyright © 2019-2024 rlaphoenix",
                "[bright_blue]https://github.com/Shivelight/vindemitor[/]",
            ),
            (0, 20, 1, 20),
            expand=True,
        ),
        justify="left",
    )

    if version:
        return


@atexit.register
def save_log():
    if console.record and LOGGING_PATH:
        # TODO: Currently semi-bust. Everything that refreshes gets duplicated.
        console.save_text(LOGGING_PATH)  # type: ignore[reportArgumentType]


if __name__ == "__main__":
    main()
