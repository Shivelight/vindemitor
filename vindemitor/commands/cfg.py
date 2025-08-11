import logging

import click

from vindemitor.core.constants import context_settings


@click.command(
    short_help="Manage configuration values for the program and its services.", context_settings=context_settings
)
@click.pass_context
def cfg(ctx: click.Context) -> None:
    log = logging.getLogger("cfg")
    log.info("TODO: show path of config used; ask user to open via `start` or $EDITOR")
