from __future__ import annotations

import logging
import random
import re
import shutil
import sys
import time
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional

import click
import yaml
from pymediainfo import MediaInfo
from rich.console import Group
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from vindemitor.core import binaries
from vindemitor.core.config import config
from vindemitor.core.console import console
from vindemitor.core.constants import DOWNLOAD_LICENCE_ONLY, context_settings
from vindemitor.core.cookies import get_cookie_jar, get_cookie_path, save_cookies
from vindemitor.core.credential import get_credentials
from vindemitor.core.drm_manager import DRMManager, get_cdm
from vindemitor.core.events import events
from vindemitor.core.post_processor import PostProcessor
from vindemitor.core.proxies import Basic, Hola, NordVPN
from vindemitor.core.proxies.proxy import Proxy
from vindemitor.core.service import Service
from vindemitor.core.services import Services
from vindemitor.core.titles import Movie, Song
from vindemitor.core.titles.episode import Episode
from vindemitor.core.track_selector import TrackSelector
from vindemitor.core.tracks import Audio, Subtitle, Tracks, Video
from vindemitor.core.utilities import is_close_match, time_elapsed_since
from vindemitor.core.utils.click_types import LANGUAGE_RANGE, QUALITY_LIST, SEASON_RANGE, ContextData, MultipleChoice
from vindemitor.core.utils.collections import merge_dict
from vindemitor.core.vaults import Vaults


class dl:
    @click.command(
        short_help="Download, Decrypt, and Mux tracks for titles from a Service.",
        cls=Services,
        context_settings=dict(**context_settings, default_map=config.dl, token_normalize_func=Services.get_tag),
    )
    @click.option(
        "-p", "--profile", type=str, default=None, help="Profile to use for Credentials and Cookies (if available)."
    )
    @click.option(
        "-q",
        "--quality",
        type=QUALITY_LIST,
        default=[],
        help="Download Resolution(s), defaults to the best available resolution.",
    )
    @click.option(
        "-v",
        "--vcodec",
        type=click.Choice(Video.Codec, case_sensitive=False),
        default=None,
        help="Video Codec to download, defaults to any codec.",
    )
    @click.option(
        "-a",
        "--acodec",
        type=click.Choice(Audio.Codec, case_sensitive=False),
        default=None,
        help="Audio Codec to download, defaults to any codec.",
    )
    @click.option(
        "-vb",
        "--vbitrate",
        type=int,
        default=None,
        help="Video Bitrate to download (in kbps), defaults to highest available.",
    )
    @click.option(
        "-ab",
        "--abitrate",
        type=int,
        default=None,
        help="Audio Bitrate to download (in kbps), defaults to highest available.",
    )
    @click.option(
        "-r",
        "--range",
        "range_",
        type=MultipleChoice(Video.Range, case_sensitive=False),
        default=[Video.Range.SDR],
        help="Video Color Range(s) to download, defaults to SDR.",
    )
    @click.option(
        "-c",
        "--channels",
        type=float,
        default=None,
        help="Audio Channel(s) to download. Matches sub-channel layouts like 5.1 with 6.0 implicitly.",
    )
    @click.option(
        "-w",
        "--wanted",
        type=SEASON_RANGE,
        default=None,
        help="Wanted episodes, e.g. `S01-S05,S07`, `S01E01-S02E03`, `S02-S02E03`, e.t.c, defaults to all.",
    )
    @click.option("-l", "--lang", type=LANGUAGE_RANGE, default="en", help="Language wanted for Video and Audio.")
    @click.option(
        "-vl",
        "--v-lang",
        type=LANGUAGE_RANGE,
        default=[],
        help="Language wanted for Video, you would use this if the video language doesn't match the audio.",
    )
    @click.option("-sl", "--s-lang", type=LANGUAGE_RANGE, default=["all"], help="Language wanted for Subtitles.")
    @click.option(
        "--proxy",
        type=str,
        default=None,
        help="Proxy URI to use. If a 2-letter country is provided, it will try get a proxy from the config.",
    )
    @click.option(
        "--tag", type=str, default=None, help="Set the Group Tag to be used, overriding the one in config if any."
    )
    @click.option(
        "--sub-format",
        type=click.Choice(Subtitle.Codec, case_sensitive=False),
        default=None,
        help="Set Output Subtitle Format, only converting if necessary.",
    )
    @click.option("-V", "--video-only", is_flag=True, default=False, help="Only download video tracks.")
    @click.option("-A", "--audio-only", is_flag=True, default=False, help="Only download audio tracks.")
    @click.option("-S", "--subs-only", is_flag=True, default=False, help="Only download subtitle tracks.")
    @click.option("-C", "--chapters-only", is_flag=True, default=False, help="Only download chapters.")
    @click.option(
        "--slow",
        is_flag=True,
        default=False,
        help="Add a 60-120 second delay between each Title download to act more like a real device. "
        "This is recommended if you are downloading high-risk titles or streams.",
    )
    @click.option(
        "--list",
        "list_",
        is_flag=True,
        default=False,
        help="Skip downloading and list available tracks and what tracks would have been downloaded.",
    )
    @click.option(
        "--list-titles",
        is_flag=True,
        default=False,
        help="Skip downloading, only list available titles that would have been downloaded.",
    )
    @click.option(
        "--skip-dl", is_flag=True, default=False, help="Skip downloading while still retrieving the decryption keys."
    )
    @click.option("--export", type=Path, help="Export Decryption Keys as you obtain them to a JSON file.")
    @click.option(
        "--cdm-only/--vaults-only",
        is_flag=True,
        default=None,
        help="Only use CDM, or only use Key Vaults for retrieval of Decryption Keys.",
    )
    @click.option("--no-proxy", is_flag=True, default=False, help="Force disable all proxy use.")
    @click.option("--no-folder", is_flag=True, default=False, help="Disable folder creation for TV Shows.")
    @click.option(
        "--no-source", is_flag=True, default=False, help="Disable the source tag from the output file name and path."
    )
    @click.option(
        "--workers",
        type=int,
        default=None,
        help="Max workers/threads to download with per-track. Default depends on the downloader.",
    )
    @click.option("--downloads", type=int, default=1, help="Amount of tracks to download concurrently.")
    @click.pass_context
    @staticmethod
    def cli(ctx: click.Context, **kwargs: Any) -> dl:
        return dl(ctx, **kwargs)

    def __init__(
        self,
        ctx: click.Context,
        no_proxy: bool,
        profile: Optional[str] = None,
        proxy: Optional[str] = None,
        tag: Optional[str] = None,
        *_: Any,
        **__: Any,
    ):
        if not ctx.invoked_subcommand:
            raise ValueError("A subcommand to invoke was not specified, the main code cannot continue.")

        self.log = logging.getLogger("download")

        self.service = Services.get_tag(ctx.invoked_subcommand)
        self.profile = profile

        if self.profile:
            self.log.info(f"Using profile: '{self.profile}'")

        with console.status("Loading Service Config...", spinner="dots"):
            service_config_path = Services.get_path(self.service) / config.filenames.config
            if service_config_path.exists():
                self.service_config = yaml.safe_load(service_config_path.read_text(encoding="utf8"))
                self.log.info("Service Config loaded")
            else:
                self.service_config = {}
            merge_dict(config.services.get(self.service), self.service_config)

        with console.status("Loading Widevine CDM...", spinner="dots"):
            try:
                self.cdm = get_cdm(self.service, self.profile)
            except ValueError as e:
                self.log.error(f"Failed to load Widevine CDM, {e}")
                sys.exit(1)
            if self.cdm:
                self.log.info(
                    f"Loaded {self.cdm.__class__.__name__} Widevine CDM: {self.cdm.system_id} (L{self.cdm.security_level})"
                )

        with console.status("Loading Key Vaults...", spinner="dots"):
            self.vaults = Vaults(self.service)
            for vault in config.key_vaults:
                vault_type = vault["type"]
                del vault["type"]
                self.vaults.load(vault_type, **vault)
            self.log.info(f"Loaded {len(self.vaults)} Vaults")

        self.proxy_providers: list[Proxy] = []
        if no_proxy:
            ctx.params["proxy"] = None
        else:
            with console.status("Loading Proxy Providers...", spinner="dots"):
                if config.proxy_providers.get("basic"):
                    self.proxy_providers.append(Basic(**config.proxy_providers["basic"]))
                if config.proxy_providers.get("nordvpn"):
                    self.proxy_providers.append(NordVPN(**config.proxy_providers["nordvpn"]))
                if binaries.HolaProxy:
                    self.proxy_providers.append(Hola())
                for proxy_provider in self.proxy_providers:
                    self.log.info(f"Loaded {proxy_provider.__class__.__name__}: {proxy_provider}")

            if proxy:
                requested_provider = None
                if re.match(r"^[a-z]+:.+$", proxy, re.IGNORECASE):
                    # requesting proxy from a specific proxy provider
                    requested_provider, proxy = proxy.split(":", maxsplit=1)
                if re.match(r"^[a-z]{2}(?:\d+)?$", proxy, re.IGNORECASE):
                    proxy = proxy.lower()
                    with console.status(f"Getting a Proxy to {proxy}...", spinner="dots"):
                        if requested_provider:
                            proxy_provider = next(
                                (x for x in self.proxy_providers if x.__class__.__name__.lower() == requested_provider),
                                None,
                            )
                            if not proxy_provider:
                                self.log.error(f"The proxy provider '{requested_provider}' was not recognised.")
                                sys.exit(1)
                            proxy_uri = proxy_provider.get_proxy(proxy)
                            if not proxy_uri:
                                self.log.error(f"The proxy provider {requested_provider} had no proxy for {proxy}")
                                sys.exit(1)
                            proxy = ctx.params["proxy"] = proxy_uri
                            self.log.info(f"Using {proxy_provider.__class__.__name__} Proxy: {proxy}")
                        else:
                            for proxy_provider in self.proxy_providers:
                                proxy_uri = proxy_provider.get_proxy(proxy)
                                if proxy_uri:
                                    proxy = ctx.params["proxy"] = proxy_uri
                                    self.log.info(f"Using {proxy_provider.__class__.__name__} Proxy: {proxy}")
                                    break
                else:
                    self.log.info(f"Using explicit Proxy: {proxy}")

        ctx.obj = ContextData(
            config=self.service_config, cdm=self.cdm, proxy_providers=self.proxy_providers, profile=self.profile
        )

        if tag:
            config.tag = tag

        # needs to be added this way instead of @cli.result_callback to be
        # able to keep `self` as the first positional
        self.cli._result_callback = self.result

    def result(
        self,
        service: Service,
        quality: list[int],
        vcodec: Optional[Video.Codec],
        acodec: Optional[Audio.Codec],
        vbitrate: int,
        abitrate: int,
        range_: list[Video.Range],
        channels: float,
        wanted: list[str],
        lang: list[str],
        v_lang: list[str],
        s_lang: list[str],
        sub_format: Optional[Subtitle.Codec],
        video_only: bool,
        audio_only: bool,
        subs_only: bool,
        chapters_only: bool,
        slow: bool,
        list_: bool,
        list_titles: bool,
        skip_dl: bool,
        export: Optional[Path],
        cdm_only: Optional[bool],
        no_proxy: bool,
        no_folder: bool,
        no_source: bool,
        workers: Optional[int],
        downloads: int,
        *_: Any,
        **__: Any,
    ) -> None:
        start_time = time.time()

        self.track_selector = TrackSelector(
            quality=quality,
            vcodec=vcodec,
            acodec=acodec,
            vbitrate=vbitrate,
            abitrate=abitrate,
            range_=range_,
            channels=channels,
            lang=lang,
            v_lang=v_lang,
            s_lang=s_lang,
            video_only=video_only,
            audio_only=audio_only,
            subs_only=subs_only,
            chapters_only=chapters_only,
        )

        if cdm_only is None:
            cdm_only = False
            vaults_only = False
        else:
            vaults_only = not cdm_only

        with console.status("Authenticating with Service...", spinner="dots"):
            cookies = get_cookie_jar(self.service, self.profile)
            credential = get_credentials(self.service, self.profile)
            service.authenticate(cookies, credential)
            if cookies or credential:
                self.log.info("Authenticated with Service")

        with console.status("Fetching Title Metadata...", spinner="dots"):
            titles = service.get_titles()
            if not titles:
                self.log.error("No titles returned, nothing to download...")
                sys.exit(1)

        console.print(Padding(Rule(f"[rule.text]{titles.__class__.__name__}: {titles}"), (1, 2)))

        console.print(Padding(titles.tree(verbose=list_titles), (0, 5)))
        if list_titles:
            return

        for i, title in enumerate(titles):
            if isinstance(title, Episode) and wanted and f"{title.season}x{title.number}" not in wanted:
                continue

            console.print(Padding(Rule(f"[rule.text]{title}"), (1, 2)))

            if slow and i != 0:
                delay = random.randint(60, 120)
                with console.status(f"Delaying by {delay} seconds..."):
                    time.sleep(delay)

            with console.status("Subscribing to events...", spinner="dots"):
                events.reset()
                events.subscribe(events.Types.SEGMENT_DOWNLOADED, service.on_segment_downloaded)
                events.subscribe(events.Types.TRACK_DOWNLOADED, service.on_track_downloaded)
                events.subscribe(events.Types.TRACK_DECRYPTED, service.on_track_decrypted)
                events.subscribe(events.Types.TRACK_REPACKED, service.on_track_repacked)
                events.subscribe(events.Types.TRACK_MULTIPLEX, service.on_track_multiplex)

            with console.status("Getting tracks...", spinner="dots"):
                title.tracks.add(service.get_tracks(title), warn_only=True)
                title.tracks.chapters = service.get_chapters(title)

            # strip SDH subs to non-SDH if no equivalent same-lang non-SDH is available
            # uses a loose check, e.g, wont strip en-US SDH sub if a non-SDH en-GB is available
            for subtitle in title.tracks.subtitles:
                if subtitle.sdh and not any(
                    is_close_match(subtitle.language, [x.language])
                    for x in title.tracks.subtitles
                    if not x.sdh and not x.forced
                ):
                    non_sdh_sub = deepcopy(subtitle)
                    non_sdh_sub.id += "_stripped"
                    non_sdh_sub.sdh = False
                    title.tracks.add(non_sdh_sub)
                    events.subscribe(
                        events.Types.TRACK_MULTIPLEX,
                        lambda track: (track.strip_hearing_impaired()) if track.id == non_sdh_sub.id else None,
                    )

            with console.status("Sorting tracks by language and bitrate...", spinner="dots"):
                title.tracks.sort_videos(by_language=v_lang or lang)
                title.tracks.sort_audio(by_language=lang)
                title.tracks.sort_subtitles(by_language=s_lang)

            if list_:
                available_tracks, _ = title.tracks.tree()
                console.print(Padding(Panel(available_tracks, title="Available Tracks"), (0, 5)))
                continue

            with console.status("Selecting tracks...", spinner="dots"):
                title.tracks = self.track_selector.select(title)

            selected_tracks, tracks_progress_callables = title.tracks.tree(add_progress=True)

            download_table = Table.grid()
            download_table.add_row(selected_tracks)
            drm_trees: dict[str, Tree] = {}
            dl_start_time = time.time()

            if skip_dl:
                DOWNLOAD_LICENCE_ONLY.set()

            def get_drm_callbacks() -> tuple[Callable, Callable, Callable]:
                """
                Creates and returns a set of callbacks for DRM status updates.
                These callbacks will update the UI table with DRM information.
                """
                tree_key = ""

                def on_pssh_init(drm: str, pssh: str):
                    if pssh not in drm_trees:
                        cek_tree = Tree(Text.assemble((drm, "cyan"), (f"({pssh})", "text"), overflow="fold"))
                        drm_trees[pssh] = cek_tree
                        download_table.add_row()
                        download_table.add_row(cek_tree)
                        nonlocal tree_key
                        tree_key = pssh

                def on_key_found(kid: str, key: str, source: str, is_track_kid: bool):
                    tree = drm_trees.get(tree_key)
                    if tree:
                        track_kid_marker = "*" if is_track_kid else ""
                        label = f"[text2]{kid}:{key}{track_kid_marker} {source}"
                        if not any(f"{kid}:{key}" in str(x.label) for x in tree.children):
                            tree.add(label)

                def on_error(message: str):
                    tree = drm_trees.get(tree_key)
                    if tree:
                        tree.add(f"[logging.level.error]{message}")

                return on_pssh_init, on_key_found, on_error

            drm_manager = DRMManager(
                self.cdm, self.vaults, cdm_only, vaults_only, service, title, export, get_drm_callbacks()
            )
            try:
                with Live(Padding(download_table, (1, 5)), console=console, refresh_per_second=5):
                    with ThreadPoolExecutor(downloads) as pool:
                        for download in futures.as_completed(
                            (
                                pool.submit(
                                    track.download,
                                    drm_manager=drm_manager,
                                    max_workers=workers,
                                    progress=tracks_progress_callables[i],
                                )
                                for i, track in enumerate(title.tracks)
                            )
                        ):
                            download.result()
            except KeyboardInterrupt:
                console.print(Padding(":x: Download Cancelled...", (0, 5, 1, 5)))
                return
            except Exception as e:  # noqa
                error_messages = [
                    ":x: Download Failed...",
                ]
                if isinstance(e, EnvironmentError):
                    error_messages.append(f"   {e}")
                else:
                    error_messages.append(
                        "   An unexpected error occurred in one of the download workers.",
                    )
                    if hasattr(e, "returncode"):
                        error_messages.append(f"   Binary call failed, Process exit code: {e.returncode}")
                    error_messages.append("   See the error trace above for more information.")

                console.print_exception()
                console.print(Padding(Group(*error_messages), (1, 5)))
                return

            if skip_dl:
                console.log("Skipped downloads as --skip-dl was used...")
            else:
                dl_time = time_elapsed_since(dl_start_time)
                console.print(Padding(f"Track downloads finished in [progress.elapsed]{dl_time}[/]", (0, 5)))

                self.post_processor = PostProcessor(no_source, no_folder, sub_format)
                with console.status("Checking Video track {video_track_n + 1} for Closed Captions..."):
                    self.post_processor._extract_closed_captions(title)
                with console.status("Converting Subtitles..."):
                    self.post_processor._convert_subtitles(title)
                with console.status("Checking Subtitles for Fonts..."):
                    self.post_processor._attach_fonts(title)
                with console.status("Repackaging tracks with FFMPEG..."):
                    self.post_processor._repackage_tracks(title)
                # TODO: user-defined post-processor?

                progress = Progress(
                    TextColumn("[progress.description]{task.description}"),
                    SpinnerColumn(finished_text=""),
                    BarColumn(),
                    "•",
                    TimeRemainingColumn(compact=True, elapsed_when_finished=True),
                    console=console,
                )

                muxed_paths: list[Path] = []
                if isinstance(title, (Movie, Episode)):
                    tasks = []
                    for video_track in title.tracks.videos or [None]:
                        task_description = "Multiplexing"
                        if video_track:
                            if len(quality) > 1:
                                task_description += f" {video_track.height}p"
                            if len(range_) > 1:
                                task_description += f" {video_track.range.name}"

                        task_id = progress.add_task(f"{task_description}...", total=None, start=False)

                        task_tracks = Tracks(title.tracks) + title.tracks.chapters + title.tracks.attachments
                        if video_track:
                            task_tracks.videos = [video_track]

                        tasks.append((task_id, task_tracks))

                    for task_id, task_tracks in tasks:
                        with Live(Padding(progress, (0, 5, 1, 5)), console=console):
                            muxed_path = self.post_processor._mux_media(
                                title, task_tracks, partial(progress.update, task_id=task_id)
                            )
                            muxed_paths.append(muxed_path)

                    for track in title.tracks:
                        track.delete()
                else:
                    # dont mux
                    muxed_paths.append(title.tracks.audio[0].path)

                for muxed_path in muxed_paths:
                    media_info = MediaInfo.parse(muxed_path)
                    final_dir = config.directories.downloads
                    final_filename = title.get_filename(media_info, show_service=not no_source)

                    if not no_folder and isinstance(title, (Episode, Song)):
                        final_dir /= title.get_filename(media_info, show_service=not no_source, folder=True)

                    final_dir.mkdir(parents=True, exist_ok=True)
                    final_path = final_dir / f"{final_filename}{muxed_path.suffix}"
                    shutil.move(muxed_path, final_path)

                title_dl_time = time_elapsed_since(dl_start_time)
                console.print(
                    Padding(f":tada: Title downloaded in [progress.elapsed]{title_dl_time}[/]!", (0, 5, 1, 5))
                )

            # update cookies
            cookie_file = get_cookie_path(self.service, self.profile)
            if cookie_file:
                save_cookies(cookie_file, service.session.cookiejar)

        dl_time = time_elapsed_since(start_time)

        console.print(Padding(f"Processed all titles in [progress.elapsed]{dl_time}", (0, 5, 1, 5)))
