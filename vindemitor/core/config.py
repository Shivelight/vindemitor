from __future__ import annotations

import os
import tempfile
from functools import cached_property
from pathlib import Path
from typing import Optional, TypeAlias

import tomlkit
from appdirs import AppDirs
from construct import ConstError
from pywidevine import Cdm as WidevineCdm
from pywidevine import Device
from pywidevine import RemoteCdm as RemoteWidevineCdm

from vindemitor.core import binaries
from vindemitor.core.proxies.basic import Basic
from vindemitor.core.proxies.hola import Hola
from vindemitor.core.proxies.nordvpn import NordVPN
from vindemitor.core.proxies.proxy import Proxy
from vindemitor.core.utils.collections import merge_dict
from vindemitor.core.vault import Vault
from vindemitor.vaults import VAULT_TYPE_MAP


class General:
    def __init__(self, data: dict | None = None):
        data = data or {}
        self.tag: str = data.get("tag", "")
        self.chapter_fallback_name: str = data.get("chapter_fallback_name", "Chapter {i:02}")
        self.set_terminal_bg: bool = data.get("set_terminal_bg", True)


class Network:
    class SessionOptions:
        def __init__(self, data: dict | None = None):
            data = data or {}
            self.headers: dict = data.get("headers", {})

    class DownloaderOptions:
        def __init__(self, data: dict | None = None):
            data = data or {}
            self.aria2c: dict = data.get(
                "aria2c",
                {
                    "max_concurrent_downloads": min(32, (os.cpu_count() or 1) + 4),
                    "max_connection_per_server": 1,
                    "split": 5,
                    "file_allocation": "prealloc",
                },
            )
            self.curl_impersonate: dict = data.get("curl_impersonate", {"browser": "chrome124"})

    class Proxies:
        def __init__(self, data: dict | None = None):
            data = data = {}

            basic_data = data.get("basic")
            self.basic: Basic | None = Basic(**basic_data) if basic_data else None

            nord_data = data.get("nordvpn")
            self.nordvpn: NordVPN | None = NordVPN(**nord_data) if nord_data else None

            self.hola: Hola | None = Hola() if binaries.HolaProxy else None

            self.loaded_providers: list[Proxy] = []
            if self.basic:
                self.loaded_providers.append(self.basic)
            if self.nordvpn:
                self.loaded_providers.append(self.nordvpn)
            if self.hola:
                self.loaded_providers.append(self.hola)

    def __init__(self, data: dict | None = None):
        data = data or {}
        self.downloader: str = data.get("downloader", "requests")
        self.session_options: Network.SessionOptions = Network.SessionOptions(data.get("session_options"))
        self.downloader_options: Network.DownloaderOptions = Network.DownloaderOptions(
            data.get("downloader_options", {})
        )
        self.proxies: Network.Proxies = Network.Proxies(data.get("proxies", {}))


class Processors:
    def __init__(self, data: dict | None = None):
        data = data or {}
        self.muxing: dict = data.get("muxing", {"set_title": True})


class LocalCdm:
    def __init__(self, widevine: str | None = None) -> None:
        if widevine:
            wvd_path = Paths.Directories.wvds / f"{widevine}.wvd"
            self._widevine_path = wvd_path
        else:
            self._widevine_path = None

    @cached_property
    def widevine(self):
        if self._widevine_path:
            return self.load_widevine(self._widevine_path)
        else:
            return None

    def load_widevine(self, path: Path):
        if not path.is_file():
            raise ValueError(f"{path} does not exist or is not a file")
        try:
            return WidevineCdm.from_device(Device.load(path))
        except ConstError as e:
            if "expected 2 but parsed 1" in str(e):
                raise ValueError(
                    f"{path.name}.wvd seems to be a v1 WVD file, use `pywidevine migrate --help` to migrate it to v2."
                )
            raise ValueError(f"{path.name}.wvd is an invalid or corrupt Widevine Device file, {e}")


class RemoteCdm:
    def __init__(self, **widevine) -> None:
        self._remote_widevine = widevine

    @cached_property
    def widevine(self) -> RemoteWidevineCdm:
        return RemoteWidevineCdm(**self._remote_widevine)


CDM_T: TypeAlias = LocalCdm | RemoteCdm


class DRM:
    def __init__(self, data: dict | None = None):
        data = data or {}
        # [drm]
        self.default_cdm: str = data.get("default_cdm", "")
        self.extra_serve_devices: list[str] = data.get("extra_serve_devices", [])

        # [drm.cdm.]
        self.cdm: dict[str, CDM_T] = {}

        lcdms: dict = data.get("cdm", {}).get("local", {})
        for lcdm_name, lcdm_data in lcdms.items():
            if lcdm_name in self.cdm:
                raise ValueError(f"Duplicate CDM keys: {lcdm_name}")
            if lcdm_data:
                self.cdm[lcdm_name] = LocalCdm(**lcdm_data)

        rcdms: dict = data.get("cdm", {}).get("remote", {})
        for rcdm_name, rcdm_data in rcdms.items():
            if rcdm_name in self.cdm:
                raise ValueError(f"Duplicate CDM keys: {rcdm_name}")
            if rcdm_data:
                self.cdm[rcdm_name] = RemoteCdm(**rcdm_data)

        # [drm.serve.]
        self.serve: dict[str, str | list[str]] = data.get("serve", {})

        # [drm.vaults.]
        self.vaults: list[Vault] = []
        vaults_data: list[dict] = data.get("vaults", [])
        for vault_data in vaults_data:
            vault_type = VAULT_TYPE_MAP[vault_data.pop("type")]
            self.vaults.append(vault_type(**vault_data))


class ClickDefaultMap:
    def __init__(self, data: dict | None = None):
        data = data or {}
        self.dl: dict = data.get("dl", {})


class Paths:
    class Directories:
        app_dirs = AppDirs("vindemitor", False)
        core_dir = Path(__file__).resolve().parent
        namespace_dir = core_dir.parent
        commands = namespace_dir / "commands"
        services = namespace_dir / "services"
        vaults = namespace_dir / "vaults"
        fonts = namespace_dir / "fonts"
        user_configs = Path(app_dirs.user_config_dir)
        data = Path(app_dirs.user_data_dir)
        downloads = Path.home() / "Downloads" / "vindemitor"
        temp = Path(tempfile.gettempdir()) / "vindemitor"
        cache = Path(app_dirs.user_cache_dir)
        cookies = data / "Cookies"
        logs = Path(app_dirs.user_log_dir)
        wvds = data / "WVDs"
        dcsl = data / "DCSL"

    class Filenames:
        log = "vindemitor_{name}_{time}.log"
        config = "config.toml"
        root_config = "vindemitor.toml"
        chapters = "Chapters_{title}_{random}.txt"
        subtitle = "Subtitle_{id}_{language}.srt"

    def __init__(self, data: dict | None = None):
        data = data or {}
        self.directories = self.Directories()
        for name, path in (data.get("directories") or {}).items():
            if path and name not in ("app_dirs", "core_dir", "namespace_dir", "user_configs", "data"):
                setattr(self.directories, name, Path(path).expanduser())

        self.filenames = self.Filenames()
        for name, filename in (data.get("filenames") or {}).items():
            if filename:
                setattr(self.filenames, name, filename)


class Config:
    def __init__(self, data: tomlkit.TOMLDocument | None = None):
        data = data or tomlkit.TOMLDocument()
        self.general = General(data.get("general"))
        self.network = Network(data.get("network"))
        self.processors = Processors(data.get("processors"))
        self.drm = DRM(data.get("drm"))
        self.default_map = ClickDefaultMap(data.get("default_map"))
        self.services: dict[str, dict] = data.get("services", {})
        self.paths = Paths(data.get("paths"))

        # legacy attributes
        self.directories = self.paths.directories
        self.filenames = self.paths.filenames

    @classmethod
    def from_toml(cls, path: Path) -> Config:
        if not path.exists():
            raise FileNotFoundError(f"Config file path ({path}) was not found")
        if not path.is_file():
            raise FileNotFoundError(f"Config file path ({path}) is not to a file.")

        doc = tomlkit.loads(path.read_text(encoding="utf8"))
        return cls(doc)


class ServiceConfig:
    def __init__(self, name: str, root_config: Config, service_config_doc: tomlkit.TOMLDocument) -> None:
        self.name: str = name
        # Configuration from service config.toml
        self.require: dict = service_config_doc.pop("require", {})
        self._service_config: dict = service_config_doc

        # vindemitor.toml
        self._root_config = root_config

        # User Configuration e.g., [services.EXAMPLE] from vindemitor.toml
        self._user_config = self._root_config.services.get(self.name, {})
        self._profile: str | None = None
        self._profiles: dict[str, dict] = self._user_config.pop("profiles", {})

        # Merge and/or override service config.toml with [services.EXAMPLE.config] from vindemitor.toml
        user_service_config = self._user_config.get("config", {})
        merge_dict(user_service_config, self._service_config)

    def _get_profile_or_user_prop(self, key: str, default=None):
        # profile specific config first
        if self.profile and (p_conf := self._profiles.get(self.profile)):
            if value := p_conf.get(key):
                return value
        # then user config
        if value := self._user_config.get(key):
            return value
        # lastly default, usually from global/root config
        return default

    @property
    def profile(self):
        return self._profile

    def set_profile(self, value: str | None):
        if value is None:
            self._profile = value
            return

        if value in self._profiles:
            self._profile = value
        else:
            raise ValueError(f"Service {self.name} has no profile called '{value}' configured")

    @property
    def cdm(self):
        cdm_name: str | None = self._get_profile_or_user_prop("cdm", self._root_config.drm.default_cdm)
        if not cdm_name:
            raise ValueError(
                f"No CDM configured for service '{self.name}'. "
                f"Please set a 'cdm' value in the profile, service config, or global config."
            )

        if cdm := self._root_config.drm.cdm.get(cdm_name):
            return cdm
        else:
            raise ValueError(
                f"{cdm_name!r} is not defined in the global DRM configuration.\n"
                f"Available CDMs: {', '.join(self._root_config.drm.cdm.keys()) or None!r}. "
                f"Profile: {self.profile or None}"
            )

    @property
    def credential(self):
        return self._get_profile_or_user_prop("credential", "")

    @property
    def downloader(self):
        return self._get_profile_or_user_prop("downloader", self._root_config.network.downloader)

    @classmethod
    def from_toml(cls, name: str, root_config: Config, path: Path) -> ServiceConfig:
        if not path.exists():
            raise FileNotFoundError(f"Service config file path ({path}) was not found")
        if not path.is_file():
            raise FileNotFoundError(f"Service config file path ({path}) is not to a file.")

        doc = tomlkit.loads(path.read_text(encoding="utf8"))
        return cls(name, root_config, doc)


# noinspection PyProtectedMember
POSSIBLE_CONFIG_PATHS = (
    # The Devine Namespace Folder (e.g., %appdata%/Python/Python311/site-packages/vindemitor)
    Paths.Directories.namespace_dir / Paths.Filenames.root_config,
    # The Parent Folder to the vindemitor Namespace Folder (e.g., %appdata%/Python/Python311/site-packages)
    Paths.Directories.namespace_dir.parent / Paths.Filenames.root_config,
    # The AppDirs User Config Folder (e.g., %localappdata%/vindemitor)
    Paths.Directories.user_configs / Paths.Filenames.root_config,
)


def get_config_path() -> Optional[Path]:
    """
    Get Path to Config from any one of the possible locations.

    Returns None if no config file could be found.
    """
    for path in POSSIBLE_CONFIG_PATHS:
        if path.exists():
            return path
    return None


config_path = get_config_path()
if config_path:
    config = Config.from_toml(config_path)
else:
    config = Config()

__all__ = ("config", "ServiceConfig")
