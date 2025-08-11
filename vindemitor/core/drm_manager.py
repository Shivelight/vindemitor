import logging
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias
from uuid import UUID

import jsonpickle

from vindemitor.core.config import CDM_T
from vindemitor.core.constants import AnyTrack
from vindemitor.core.drm import DRM_T
from vindemitor.core.drm.widevine import Widevine
from vindemitor.core.service import Service
from vindemitor.core.session import ServiceSession
from vindemitor.core.titles import Title_T
from vindemitor.core.vaults import Vaults

DrmCallbacks: TypeAlias = tuple[
    Callable[[str, str], None], Callable[[str, str, str, bool], None], Callable[[str], None]
]


def _NOOP(*_):
    pass


_NOOPS = (_NOOP, _NOOP, _NOOP)


class DRMManager:
    """Handles DRM operations like key retrieval from vaults and CDMs."""

    def __init__(
        self,
        cdm: CDM_T | None,
        vaults: Vaults,
        cdm_only: bool,
        vaults_only: bool,
        service: Service,
        title: Title_T,
        export: Path | None = None,
        callbacks: DrmCallbacks = _NOOPS,
    ):
        self.cdm = cdm
        self.vaults = vaults
        self.cdm_only = cdm_only
        self.vaults_only = vaults_only
        self.service = service
        self.title = title
        self.export = export
        self.on_pssh_init, self.on_key_found, self.on_error = callbacks
        self.log = logging.getLogger("drm")

    def prepare_drm_keys(
        self,
        track: AnyTrack,
        track_kid: UUID | None = None,
        custom_drm: DRM_T | None = None,
    ) -> Widevine | None:
        """Prepare the DRM by getting decryption data using callbacks for status."""
        drm = None
        if track.drm:
            for drm in track.drm:
                drm = drm

        if custom_drm:
            drm = custom_drm

        if not drm or not isinstance(drm, Widevine):
            return

        if self.cdm and self.cdm.widevine is None:
            raise ValueError("Widevine CDM is required.")

        self.on_pssh_init("Widevine", drm.pssh.dumps())

        for kid in drm.kids:
            if kid in drm.content_keys:
                continue
            is_track_kid = kid == track_kid

            if not self.cdm_only:
                content_key, vault_used = self.vaults.get_key(kid)
                if content_key:
                    drm.content_keys[kid] = content_key
                    self.on_key_found(kid.hex, content_key, f"from {vault_used}", is_track_kid)
                    self.vaults.add_key(kid, content_key, excluding=vault_used)
                elif self.vaults_only:
                    msg = f"No Vault has a Key for {kid.hex} and --vaults-only was used"
                    self.on_error(msg)
                    raise Widevine.Exceptions.CEKNotFound(msg)

            if kid not in drm.content_keys and not self.vaults_only:
                from_vaults = drm.content_keys.copy()
                try:
                    drm.get_content_keys(
                        cdm=self.cdm.widevine,  # pyright: ignore[reportArgumentType, reportOptionalMemberAccess]
                        certificate=lambda challenge: self.service.get_widevine_service_certificate(
                            challenge=challenge, title=self.title, track=track
                        ),
                        licence=lambda challenge: self.service.get_widevine_license(
                            challenge=challenge, title=self.title, track=track
                        ),
                    )
                except Exception as e:
                    msg = (
                        str(e)
                        if isinstance(e, (Widevine.Exceptions.EmptyLicense, Widevine.Exceptions.CEKNotFound))
                        else f"An exception occurred: {e}"
                    )
                    self.on_error(msg)
                    raise
                for kid_, key in drm.content_keys.items():
                    self.on_key_found(kid_.hex, key, "from CDM", is_track_kid)

                drm.content_keys.update(from_vaults)
                keys_to_cache: dict[UUID | str, str] = {
                    k: v for k, v in drm.content_keys.items() if v and v.count("0") != len(v)
                }
                if successful_caches := self.vaults.add_keys(keys_to_cache):
                    self.log.info(f"Cached {successful_caches} Key(s) to {len(self.vaults)} Vaults")
                break

        if track_kid and track_kid not in drm.content_keys:
            msg = f"No Content Key for KID {track_kid.hex} was returned"
            self.on_error(msg)
            raise Widevine.Exceptions.CEKNotFound(msg)

        # TODO: is jsonpickle really necessary?
        if self.export and drm.content_keys:
            keys = jsonpickle.loads(self.export.read_text(encoding="utf8")) if self.export.is_file() else {}
            title_key, track_key = str(self.title), str(track)
            keys.setdefault(title_key, {}).setdefault(track_key, {}).update(
                {k.hex: v for k, v in drm.content_keys.items()}
            )
            self.export.write_text(jsonpickle.dumps(keys, indent=4), encoding="utf8")  # type: ignore

        return drm

    def get_session(self) -> ServiceSession:
        """Shortcut to get underlying service session"""
        return self.service.session
