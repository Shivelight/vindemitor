from typing import Union

from vindemitor.core.drm.clearkey import ClearKey
from vindemitor.core.drm.widevine import Widevine

DRM_T = Union[ClearKey, Widevine]


__all__ = ("ClearKey", "Widevine", "DRM_T")
