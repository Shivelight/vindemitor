from typing import Type

from vindemitor.core.vault import Vault
from vindemitor.vaults.API import API
from vindemitor.vaults.MySQL import MySQL
from vindemitor.vaults.SQLite import SQLite

VAULT_TYPE_MAP: dict[str, Type[Vault]] = {API.__name__: API, MySQL.__name__: MySQL, SQLite.__name__: SQLite}

__all__ = ("API", "MySQL", "SQLite")
