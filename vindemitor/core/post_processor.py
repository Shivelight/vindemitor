import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from vindemitor.core import binaries
from vindemitor.core.events import events
from vindemitor.core.titles.song import Song
from vindemitor.core.utils.xml import matroska_tags_xml

from .config import config
from .titles import Title_T
from .tracks import Subtitle, Tracks
from .tracks.attachment import Attachment
from .utilities import get_system_fonts
from .utils.subprocess import ffprobe


class PostProcessor:
    """Handles post-download processing like muxing, conversion, etc."""

    def __init__(
        self,
        no_source: bool = False,
        no_folder: bool = False,
        sub_format: Any = None,
    ):
        self.no_source = no_source
        self.no_folder = no_folder
        self.sub_format = sub_format
        self.log = logging.getLogger("postprocessor")

    def process(self, title: Title_T):
        """Run the full post-processing pipeline for a title."""
        raise NotImplementedError

    def _extract_closed_captions(self, title: Title_T):
        video_track_n = 0
        while (
            not title.tracks.subtitles
            and len(title.tracks.videos) > video_track_n
            and any(
                x.get("codec_name", "").startswith("eia_")
                for x in ffprobe(title.tracks.videos[video_track_n].path).get("streams", [])
            )
        ):
            try:
                # TODO: Figure out the real language, it might be different
                #       EIA-CC tracks sadly don't carry language information :(
                # TODO: Figure out if the CC language is original lang or not.
                #       Will need to figure out above first to do so.
                video_track = title.tracks.videos[video_track_n]
                track_id = f"ccextractor-{video_track.id}"
                cc_lang = title.language or video_track.language
                cc = video_track.ccextractor(
                    track_id=track_id,
                    out_path=config.directories.temp / config.filenames.subtitle.format(id=track_id, language=cc_lang),
                    language=cc_lang,
                    original=False,
                )
                if cc:
                    # will not appear in track listings as it's added after all times it lists
                    title.tracks.add(cc)
                    self.log.info(f"Extracted a Closed Caption from Video track {video_track_n + 1}")
            except EnvironmentError:
                self.log.error("Cannot extract Closed Captions as ccextractor executable was not found.")
                break
            video_track_n += 1

    def _convert_subtitles(self, title: Title_T):
        for subtitle in title.tracks.subtitles:
            if self.sub_format and subtitle.codec != self.sub_format:
                subtitle.convert(self.sub_format)
            elif subtitle.codec == Subtitle.Codec.TimedTextMarkupLang:
                # MKV does not support TTML, VTT is the next best option
                subtitle.convert(Subtitle.Codec.WebVTT)

    def _attach_fonts(self, title: Title_T):
        font_names = []
        for subtitle in title.tracks.subtitles:
            if subtitle.codec == Subtitle.Codec.SubStationAlphav4:
                font_names.extend(
                    line.removesuffix("Style: ").split(",")[1]
                    for line in subtitle.path.read_text("utf8").splitlines()
                    if line.startswith("Style: ")
                )

        font_count = 0
        system_fonts = get_system_fonts()
        for font_name in set(font_names):
            family_dir = Path(config.directories.fonts, font_name)
            fonts_from_system = [file for name, file in system_fonts.items() if name.startswith(font_name)]
            if family_dir.exists():
                for font in family_dir.glob("*.*tf"):
                    title.tracks.add(Attachment(font, f"{font_name} ({font.stem})"))
                    font_count += 1
            elif fonts_from_system:
                for font in fonts_from_system:
                    title.tracks.add(Attachment(font, f"{font_name} ({font.stem})"))
                    font_count += 1
            else:
                self.log.warning(f"Subtitle uses font [text2]{font_name}[/] but it could not be found...")
        if font_count:
            self.log.info(f"Attached {font_count} fonts for the Subtitles")

    def _repackage_tracks(self, title: Title_T):
        has_repacked = False
        for track in title.tracks:
            if track.needs_repack:
                track.repackage()
                has_repacked = True
                events.emit(events.Types.TRACK_REPACKED, track=track)
        if has_repacked:
            # we don't want to fill up the log with "Repacked x track"
            self.log.info("Repacked one or more tracks with FFMPEG")

    def _mux(self, title: Title_T, tracks: Tracks, progress_callback) -> Path:
        if not binaries.MkvMerge:
            raise EnvironmentError("mkvmerge not found but is required!")
        muxed_path, return_code, errors = tracks.mux(str(title), progress=progress_callback, delete=False)
        if return_code >= 2:
            self.log.error(f"Failed to Mux video to Matroska file ({return_code}):")
        elif return_code == 1 or errors:
            self.log.warning("mkvmerge had at least one warning or error, continuing anyway...")
        for line in errors:
            if line.startswith("#GUI#error"):
                self.log.error(line)
            else:
                self.log.warning(line)
        if return_code >= 2:
            sys.exit(1)
        for video_track in tracks.videos:
            video_track.delete()

        return muxed_path

    def _tags_matroska(self, path, title: Title_T):
        if not config.processors.tags_matroska["enable"]:
            return

        if isinstance(title, Song):
            return

        if not binaries.MkvPropEdit:
            self.log.info("mkvpropedit not found. Continuing without tags.")
            return

        if config.processors.tags_matroska["tag_group"]:
            title.matroska_tags["Group"] = config.general.tag

        if title.matroska_tags:
            tags_xml = matroska_tags_xml(title.matroska_tags)

            with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
                f.write(tags_xml)
                tmp_path = Path(f.name)
                # run subprocess outside context manager to make sure the file is closed first on Windows

            subprocess.run(
                [binaries.MkvPropEdit, path, "--tags", f"global:{tmp_path}"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            tmp_path.unlink(missing_ok=True)
