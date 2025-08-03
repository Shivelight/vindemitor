import html
from http.cookiejar import CookieJar, MozillaCookieJar
from pathlib import Path
from typing import Optional

from vindemitor.core.config import config


def get_cookie_path(service: str, profile: Optional[str]) -> Optional[Path]:
    """Get Service Cookie File Path for Profile."""
    direct_cookie_file = config.directories.cookies / f"{service}.txt"
    profile_cookie_file = config.directories.cookies / service / f"{profile}.txt"
    default_cookie_file = config.directories.cookies / service / "default.txt"

    if direct_cookie_file.exists():
        return direct_cookie_file
    elif profile_cookie_file.exists():
        return profile_cookie_file
    elif default_cookie_file.exists():
        return default_cookie_file


def get_cookie_jar(service: str, profile: Optional[str]) -> Optional[MozillaCookieJar]:
    """Get Service Cookies for Profile."""
    cookie_file = get_cookie_path(service, profile)
    if cookie_file:
        cookie_jar = MozillaCookieJar(cookie_file)
        cookie_data = html.unescape(cookie_file.read_text("utf8")).splitlines(keepends=False)
        for i, line in enumerate(cookie_data):
            if line and not line.startswith("#"):
                line_data = line.lstrip().split("\t")
                # Disable client-side expiry checks completely across everywhere
                # Even though the cookies are loaded under ignore_expires=True, stuff
                # like python-requests may not use them if they are expired
                line_data[4] = ""
                cookie_data[i] = "\t".join(line_data)
        cookie_data = "\n".join(cookie_data)
        cookie_file.write_text(cookie_data, "utf8")
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        return cookie_jar


def save_cookies(path: Path, cookies: CookieJar):
    cookie_jar = MozillaCookieJar(path)
    cookie_jar.load()
    for cookie in cookies:
        cookie_jar.set_cookie(cookie)
    cookie_jar.save(ignore_discard=True)
