import shutil
import sys
from pathlib import Path
from typing import Optional


def find(*names: str) -> Optional[Path]:
    """Find the path of the first found binary name."""
    for name in names:
        path = shutil.which(name)
        if path:
            return Path(path)
    return None


FFMPEG = find("ffmpeg")
FFProbe = find("ffprobe")
FFPlay = find("ffplay")
MkvMerge = find("mkvmerge")
MkvPropEdit = find("mkvpropedit")
SubtitleEdit = find("SubtitleEdit")
__shaka_platform = {"win32": "win", "darwin": "osx", "linux": "linux"}.get(sys.platform, sys.platform)
ShakaPackager = find(
    "shaka-packager",
    "packager",
    f"packager-{__shaka_platform}",
    f"packager-{__shaka_platform}-arm64",
    f"packager-{__shaka_platform}-x64",
)
Mp4Decrypt = find("mp4decrypt")
Aria2 = find("aria2c", "aria2")
CCExtractor = find("ccextractor", "ccextractorwin", "ccextractorwinfull")
HolaProxy = find("hola-proxy")
MPV = find("mpv")

__all__ = (
    "FFMPEG",
    "FFProbe",
    "FFPlay",
    "MkvMerge",
    "MkvPropEdit",
    "SubtitleEdit",
    "ShakaPackager",
    "Mp4Decrypt",
    "Aria2",
    "CCExtractor",
    "HolaProxy",
    "MPV",
    "find",
)
