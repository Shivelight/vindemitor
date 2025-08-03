import math
from itertools import product

from vindemitor.core.titles import Episode, Movie, Title_T
from vindemitor.core.tracks import Tracks
from vindemitor.core.tracks.audio import Audio
from vindemitor.core.tracks.video import Video
from vindemitor.core.utilities import is_close_match


class TrackSelector:
    """Selects tracks based on user-defined criteria."""

    def __init__(
        self,
        quality: list[int],
        vcodec: Video.Codec | None,
        acodec: Audio.Codec | None,
        vbitrate: int,
        abitrate: int,
        range_: list[Video.Range],
        channels: float,
        lang: list[str],
        v_lang: list[str],
        s_lang: list[str],
        video_only: bool,
        audio_only: bool,
        subs_only: bool,
        chapters_only: bool,
    ):
        self.vcodec = vcodec
        self.range_ = range_
        self.vbitrate = vbitrate
        self.v_lang = v_lang
        self.lang = lang
        self.quality = quality
        self.s_lang = s_lang
        self.acodec = acodec
        self.abitrate = abitrate
        self.channels = channels
        self.video_only = video_only
        self.audio_only = audio_only
        self.subs_only = subs_only
        self.chapters_only = chapters_only

    def select(self, title: Title_T) -> Tracks:
        """Selects and returns a new Tracks object with filtered tracks."""
        tracks = title.tracks

        if isinstance(title, (Movie, Episode)):
            if self.vcodec:
                tracks.select_video(lambda x: x.codec == self.vcodec)
            if self.range_:
                tracks.select_video(lambda x: x.range in self.range_)
            if self.vbitrate:
                tracks.select_video(lambda x: x.bitrate is not None and (x.bitrate // 1000 == self.vbitrate))

            video_languages = self.v_lang or self.lang
            if video_languages and "all" not in video_languages:
                tracks.videos = tracks.by_language(tracks.videos, video_languages)

            if self.quality:
                tracks.by_resolutions(self.quality)

            tracks.videos = [
                track
                for resolution, color_range in product(self.quality or [None], self.range_ or [None])
                if (
                    track := next(
                        (
                            t
                            for t in tracks.videos
                            if (not resolution and not color_range)
                            or (
                                (
                                    not resolution
                                    or t.height == resolution
                                    or (t.width is not None and int(t.width * (9 / 16)) == resolution)
                                )
                                and (not color_range or t.range == color_range)
                            )
                        ),
                        None,
                    )
                )
            ] or tracks.videos

            if self.s_lang and "all" not in self.s_lang:
                tracks.select_subtitles(lambda x: is_close_match(x.language, self.s_lang))
            tracks.select_subtitles(lambda x: not x.forced or is_close_match(x.language, self.lang or []))

        if tracks.audio:
            tracks.select_audio(lambda x: not x.descriptive)
            if self.acodec:
                tracks.select_audio(lambda x: x.codec == self.acodec)
            if self.abitrate:
                tracks.select_audio(lambda x: x.bitrate is not None and (x.bitrate // 1000 == self.abitrate))
            if self.channels is not None:
                tracks.select_audio(
                    lambda x: x.channels is not None and math.ceil(x.channels) == math.ceil(self.channels)
                )

            if self.lang and "all" not in self.lang:
                tracks.audio = tracks.by_language(tracks.audio, self.lang, per_language=1)

        if self.video_only or self.audio_only or self.subs_only or self.chapters_only:
            kept_tracks = []
            if self.video_only:
                kept_tracks.extend(tracks.videos)
            if self.audio_only:
                kept_tracks.extend(tracks.audio)
            if self.subs_only:
                kept_tracks.extend(tracks.subtitles)
            if self.chapters_only:
                kept_tracks.extend(tracks.chapters)
            return Tracks(kept_tracks)

        return tracks
