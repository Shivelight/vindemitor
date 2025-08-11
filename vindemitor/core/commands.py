from typing import Optional

import click

from vindemitor.core.config import config
from vindemitor.core.utilities import import_module_by_path

_COMMANDS = sorted(
    (path for path in config.paths.directories.commands.glob("*.py") if path.stem.lower() != "__init__"),
    key=lambda x: x.stem,
)

_MODULES = {path.stem: getattr(import_module_by_path(path), path.stem) for path in _COMMANDS}


class Commands(click.Group):
    """Lazy-loaded command group of project commands."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Returns a list of command names from the command filenames."""
        return [x.stem for x in _COMMANDS]

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        """Load the command code and return the main click command function."""
        module = _MODULES.get(cmd_name)
        if not module:
            raise click.ClickException(f"Unable to find command by the name '{cmd_name}'")

        if hasattr(module, "cli"):
            return module.cli

        return module


# Hide direct access to commands from quick import form, they shouldn't be accessed directly
__all__ = ("Commands",)
