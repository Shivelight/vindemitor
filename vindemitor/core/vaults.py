from typing import Iterator, Optional, Union
from uuid import UUID

from vindemitor.core.config import config
from vindemitor.core.vault import Vault


class Vaults:
    """Keeps hold of Key Vaults with convenience functions, e.g. searching all vaults."""

    def __init__(self, default_service: Optional[str] = None):
        self.default_service = default_service or ""
        self.vaults: list[Vault] = config.drm.vaults

    def __iter__(self) -> Iterator[Vault]:
        return iter(self.vaults)

    def __len__(self) -> int:
        return len(self.vaults)

    def get_key(self, kid: Union[UUID, str], service: str | None = None) -> tuple[Optional[str], Optional[Vault]]:
        """Get Key from the first Vault it can by KID (Key ID) and Service."""
        service = service or self.default_service
        for vault in self.vaults:
            key = vault.get_key(kid, service)
            if key and key.count("0") != len(key):
                return key, vault
        return None, None

    def add_key(
        self, kid: Union[UUID, str], key: str, excluding: Optional[Vault] = None, service: str | None = None
    ) -> int:
        """Add a KID:KEY to all Vaults, optionally with an exclusion."""
        service = service or self.default_service
        success = 0
        for vault in self.vaults:
            if vault != excluding:
                try:
                    success += vault.add_key(service, kid, key)
                except (PermissionError, NotImplementedError):
                    pass
        return success

    def add_keys(self, kid_keys: dict[Union[UUID, str], str], service: str | None = None) -> int:
        """
        Add multiple KID:KEYs to all Vaults. Duplicate Content Keys are skipped.
        PermissionErrors when the user cannot create Tables are absorbed and ignored.
        """
        success = 0
        for vault in self.vaults:
            try:
                success += vault.add_keys(self.service, kid_keys)
            except (PermissionError, NotImplementedError):
                pass
        return success


__all__ = ("Vaults",)
