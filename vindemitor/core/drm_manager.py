import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TypeAlias
from uuid import UUID

import jsonpickle
from construct import ConstError
from pywidevine import Device, RemoteCdm
from pywidevine.cdm import Cdm as WidevineCdm

from vindemitor.core.config import config
from vindemitor.core.drm import DRM_T
from vindemitor.core.drm.widevine import Widevine
from vindemitor.core.titles import Title_T
from vindemitor.core.tracks import Track
from vindemitor.core.vaults import Vaults

DrmCallbacks: TypeAlias = tuple[
    Callable[[str, str], None], Callable[[str, str, str, bool], None], Callable[[str], None]
]


class DRMManager:
    """Handles DRM operations like key retrieval from vaults and CDMs."""

    def __init__(self, cdm: WidevineCdm | None, vaults: Vaults):
        self.cdm = cdm
        self.vaults = vaults
        self.log = logging.getLogger("drm")

    def get_prepare_drm_partial(
        self,
        track: Track,
        title: Title_T,
        certificate: Callable,
        licence: Callable,
        drm_callbacks: DrmCallbacks,
        cdm_only: bool,
        vaults_only: bool,
        export: Path | None,
    ) -> partial:
        """Returns a partial function for preparing DRM for a specific track."""
        on_pssh_init, on_key_found, on_error = drm_callbacks
        return partial(
            self.prepare_drm,
            track=track,
            title=title,
            certificate=certificate,
            licence=licence,
            on_pssh_init=on_pssh_init,
            on_key_found=on_key_found,
            on_error=on_error,
            cdm_only=cdm_only,
            vaults_only=vaults_only,
            export=export,
        )

    def prepare_drm(
        self,
        drm: DRM_T,
        track: Track,
        title: Title_T,
        certificate: Callable,
        licence: Callable,
        on_pssh_init: Callable[[str, str], None],
        on_key_found: Callable[[str, str, str, bool], None],
        on_error: Callable[[str], None],
        track_kid: UUID | None = None,
        cdm_only: bool = False,
        vaults_only: bool = False,
        export: Path | None = None,
    ) -> None:
        """Prepare the DRM by getting decryption data using callbacks for status."""
        if not drm or not isinstance(drm, Widevine):
            return

        on_pssh_init("Widevine", drm.pssh.dumps())

        for kid in drm.kids:
            if kid in drm.content_keys:
                continue
            is_track_kid = kid == track_kid

            if not cdm_only:
                content_key, vault_used = self.vaults.get_key(kid)
                if content_key:
                    drm.content_keys[kid] = content_key
                    on_key_found(kid.hex, content_key, f"from {vault_used}", is_track_kid)
                    self.vaults.add_key(kid, content_key, excluding=vault_used)
                elif vaults_only:
                    msg = f"No Vault has a Key for {kid.hex} and --vaults-only was used"
                    on_error(msg)
                    raise Widevine.Exceptions.CEKNotFound(msg)

            if kid not in drm.content_keys and not vaults_only:
                from_vaults = drm.content_keys.copy()
                try:
                    drm.get_content_keys(cdm=self.cdm, licence=licence, certificate=certificate)
                except Exception as e:
                    msg = (
                        str(e)
                        if isinstance(e, (Widevine.Exceptions.EmptyLicense, Widevine.Exceptions.CEKNotFound))
                        else f"An exception occurred: {e}"
                    )
                    on_error(msg)
                    raise
                for kid_, key in drm.content_keys.items():
                    on_key_found(kid_.hex, key, "from CDM", is_track_kid)

                drm.content_keys.update(from_vaults)
                keys_to_cache = {k: v for k, v in drm.content_keys.items() if v and v.count("0") != len(v)}
                if successful_caches := self.vaults.add_keys(keys_to_cache):
                    self.log.info(f"Cached {successful_caches} Key(s) to {len(self.vaults)} Vaults")
                break

        if track_kid and track_kid not in drm.content_keys:
            msg = f"No Content Key for KID {track_kid.hex} was returned"
            on_error(msg)
            raise Widevine.Exceptions.CEKNotFound(msg)

        if export and drm.content_keys:
            keys = jsonpickle.loads(export.read_text(encoding="utf8")) if export.is_file() else {}
            title_key, track_key = str(title), str(track)
            keys.setdefault(title_key, {}).setdefault(track_key, {}).update(
                {k.hex: v for k, v in drm.content_keys.items()}
            )
            export.write_text(jsonpickle.dumps(keys, indent=4), encoding="utf8")


def get_cdm(service: str, profile: str | None = None) -> WidevineCdm | None:
    """
    Get CDM for a specified service (either Local or Remote CDM).
    Raises a ValueError if there's a problem getting a CDM.
    """
    cdm_name = config.cdm.get(service) or config.cdm.get("default")
    if not cdm_name:
        return None

    if isinstance(cdm_name, dict):
        if not profile:
            return None
        cdm_name = cdm_name.get(profile) or config.cdm.get("default")
        if not cdm_name:
            return None

    cdm_api = next(iter(x for x in config.remote_cdm if x["name"] == cdm_name), None)
    if cdm_api:
        del cdm_api["name"]
        return RemoteCdm(**cdm_api)

    cdm_path = config.directories.wvds / f"{cdm_name}.wvd"
    if not cdm_path.is_file():
        raise ValueError(f"{cdm_name} does not exist or is not a file")

    try:
        device = Device.load(cdm_path)
    except ConstError as e:
        if "expected 2 but parsed 1" in str(e):
            raise ValueError(
                f"{cdm_name}.wvd seems to be a v1 WVD file, use `pywidevine migrate --help` to migrate it to v2."
            )
        raise ValueError(f"{cdm_name}.wvd is an invalid or corrupt Widevine Device file, {e}")

    return WidevineCdm.from_device(device)
