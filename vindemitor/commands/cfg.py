import logging
import os
import subprocess
import sys

import click

from vindemitor.core.config import get_config_path
from vindemitor.core.constants import context_settings


@click.command(
    short_help="Manage configuration values for the program and its services.", context_settings=context_settings
)
@click.option("--open", is_flag=True, default=False, help="Open configuration file")
@click.pass_context
def cfg(ctx: click.Context, open: bool) -> None:
    log = logging.getLogger("cfg")
    config_path = get_config_path()
    log.info(f"Config loaded: {config_path}")
    if config_path and open:
        if sys.platform == "win32":
            os.startfile(config_path)
        elif sys.platform == "linux":
            subprocess.call(("xdg-open", config_path))
        elif sys.platform == "darwin":
            subprocess.call(("open", config_path))
