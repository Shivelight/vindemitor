from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping
from typing import Any

import httpx
import requests
import requests.cookies


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
    def cookies(self) -> Any:
        """Get the session cookies."""
        raise NotImplementedError

    @cookies.setter
    @abstractmethod
    def cookies(self, cookies: Any) -> None:
        """Set the session cookies."""
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
    def proxies(self) -> dict[str, str]:
        """Get the session proxies."""
        raise NotImplementedError

    @proxies.setter
    @abstractmethod
    def proxies(self, proxies: dict[str, str]) -> None:
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
    def cookies(self) -> requests.cookies.RequestsCookieJar:
        return self.session.cookies

    @cookies.setter
    def cookies(self, cookies: dict[str, str] | requests.cookies.RequestsCookieJar) -> None:
        if isinstance(cookies, dict):
            self.session.cookies.update(cookies)
        else:
            self.session.cookies = cookies

    @property
    def headers(self) -> MutableMapping:
        return self.session.headers

    @headers.setter
    def headers(self, headers: MutableMapping) -> None:
        self.session.headers = headers

    @property
    def proxies(self) -> dict[str, str]:
        return dict(self.session.proxies)

    @proxies.setter
    def proxies(self, proxies: dict[str, str]) -> None:
        self.session.proxies.update(proxies)


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
    def cookies(self, cookies: dict[str, str] | httpx.Cookies) -> None:
        if isinstance(cookies, dict):
            self.session.cookies.update(cookies)
        else:
            self.session.cookies = cookies

    @property
    def headers(self) -> MutableMapping:
        return self.session.headers

    @headers.setter
    def headers(self, headers: MutableMapping) -> None:
        self.session.headers = headers

    @property
    def proxies(self) -> dict[str, str]:
        raise NotImplementedError

    @proxies.setter
    def proxies(self, proxies: dict[str, str]) -> None:
        raise NotImplementedError


DefaultSession = RequestsSession
