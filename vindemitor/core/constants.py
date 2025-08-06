from threading import Event
from typing import TYPE_CHECKING, TypeVar, Union

if TYPE_CHECKING:
    from vindemitor.core.tracks.audio import Audio
    from vindemitor.core.tracks.subtitle import Subtitle
    from vindemitor.core.tracks.track import Track
    from vindemitor.core.tracks.video import Video

DOWNLOAD_CANCELLED = Event()
DOWNLOAD_LICENCE_ONLY = Event()

DRM_SORT_MAP = ["ClearKey", "Widevine"]
LANGUAGE_MAX_DISTANCE = 5  # this is max to be considered "same", e.g., en, en-US, en-AU
VIDEO_CODEC_MAP = {"AVC": "H.264", "HEVC": "H.265"}
DYNAMIC_RANGE_MAP = {"HDR10": "HDR", "HDR10+": "HDR", "Dolby Vision": "DV"}
AUDIO_CODEC_MAP = {"E-AC-3": "DDP", "AC-3": "DD"}

context_settings = dict(
    help_option_names=["-?", "-h", "--help"],  # default only has --help
    max_content_width=116,  # max PEP8 line-width, -4 to adjust for initial indent
)

# For use in signatures of functions which take one specific type of track at a time
# (it can't be a list that contains e.g. both Video and Audio objects)
TrackT = TypeVar("TrackT", bound="Track")

# For general use in lists that can contain mixed types of tracks.
# list[Track] won't work because list is invariant.
# TODO: Add Chapter?
AnyTrack = Union["Video", "Audio", "Subtitle"]
