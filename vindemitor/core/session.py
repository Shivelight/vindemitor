from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping
from http.cookiejar import CookieJar
from typing import Any

import httpcore
import httpx
import requests
from httpx._utils import URLPattern
from requests.cookies import RequestsCookieJar


class ServiceSession(ABC):
    """Base class defining the interface for Service HTTP session implementations.

    This class allows a service to provide its own HTTP client implementation
    for fetching manifests and licenses.

    This is primarily intended as a workaround for connection issues that would otherwise
    require configuring SSLCipher or other complex workaround.
    """

    @abstractmethod
    def get(self, url: str, **kwargs: Any) -> Any:
        """Perform a GET request."""
        raise NotImplementedError

    @abstractmethod
    def post(self, url: str, data: Any = None, json: Any = None, **kwargs: Any) -> Any:
        """Perform a POST request."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close the session."""
        raise NotImplementedError

    @property
    @abstractmethod
    def cookies(self) -> MutableMapping:
        """Get the session cookies."""
        raise NotImplementedError

    @cookies.setter
    @abstractmethod
    def cookies(self, cookies: MutableMapping | CookieJar) -> None:
        """Set the session cookies."""
        raise NotImplementedError

    @property
    @abstractmethod
    def cookiejar(self) -> CookieJar:
        """Get session underlying CookieJar.

        This meant to be used internally. Using this directly on services code is discouraged.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def headers(self) -> MutableMapping:
        """Get the session headers."""
        raise NotImplementedError

    @headers.setter
    @abstractmethod
    def headers(self, headers: MutableMapping) -> None:
        """Set the session headers."""
        raise NotImplementedError

    @property
    @abstractmethod
    def proxy(self) -> str | None:
        """Get the session proxies."""
        raise NotImplementedError

    @proxy.setter
    @abstractmethod
    def proxy(self, proxy: str) -> None:
        """Set the session proxies."""
        raise NotImplementedError


class RequestsSession(ServiceSession):
    """Session implementation using requests library."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session: requests.Session = session or requests.Session()

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.session.get(url, **kwargs)

    def post(self, url: str, data: Any = None, json: Any = None, **kwargs: Any) -> requests.Response:
        return self.session.post(url, data=data, json=json**kwargs)

    def close(self) -> None:
        self.session.close()

    @property
    def cookies(self) -> RequestsCookieJar:
        return self.session.cookies

    @cookies.setter
    def cookies(self, cookies: MutableMapping | CookieJar) -> None:
        if isinstance(cookies, MutableMapping):
            self.session.cookies.update(cookies)
        else:
            self.session.cookies = cookies  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def cookiejar(self) -> CookieJar:
        return self.session.cookies

    @property
    def headers(self) -> MutableMapping:
        return self.session.headers

    @headers.setter
    def headers(self, headers: MutableMapping) -> None:
        self.session.headers = headers

    @property
    def proxy(self) -> str | None:
        return self.session.proxies["all"]

    @proxy.setter
    def proxy(self, proxy: str) -> None:
        self.session.proxies.update({"all": proxy})


class HTTPXSession(ServiceSession):
    """Session implementation using HTTPX library."""

    def __init__(self, session: httpx.Client | None = None) -> None:
        self.session: httpx.Client = session or httpx.Client()

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.session.get(url, **kwargs)

    def post(self, url: str, data: Any = None, json: Any = None, **kwargs: Any) -> httpx.Response:
        if data is not None and not isinstance(data, Mapping):
            kwargs["content"] = data
            data = None
        return self.session.post(url, data=data, json=json, **kwargs)

    def close(self) -> None:
        self.session.close()

    @property
    def cookies(self) -> httpx.Cookies:
        return self.session.cookies

    @cookies.setter
    def cookies(self, cookies: MutableMapping | CookieJar) -> None:
        if isinstance(cookies, MutableMapping):
            self.session.cookies.update(cookies)  # pyright: ignore[reportArgumentType]
        else:
            self.session.cookies.jar = cookies

    @property
    def cookiejar(self) -> CookieJar:
        return self.session.cookies.jar

    @property
    def headers(self) -> MutableMapping:
        return self.session.headers

    @headers.setter
    def headers(self, headers: MutableMapping) -> None:
        self.session.headers = headers

    @property
    def proxy(self) -> str | None:
        if mount := self.session._mounts.get(URLPattern("all://")):
            if isinstance(mount, httpx.HTTPTransport) and isinstance(mount._pool, httpcore.HTTPProxy):
                proxy_url = mount._pool._proxy_url
                if proxy_url.port is None:
                    return f"{proxy_url.scheme}://{proxy_url.host}{proxy_url.target}"
                return f"{proxy_url.scheme}://{proxy_url.host}:{proxy_url.port}{proxy_url.target}"

    @proxy.setter
    def proxy(self, proxy: str) -> None:
        new_proxy_transport = self.session._init_proxy_transport(httpx.Proxy(proxy))
        self.session._mounts.update({URLPattern("all://"): new_proxy_transport})


DefaultSession = RequestsSession
