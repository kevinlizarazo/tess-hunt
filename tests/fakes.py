"""A stand-in for requests.Session that serves canned responses."""

import requests


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content


class FakeSession:
    """Serves `sequence` in order first, then `routes` by URL; anything else is a 404."""

    def __init__(self, routes=None, sequence=None):
        self.routes = routes or {}
        self.sequence = list(sequence or [])
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        if self.sequence:
            item = self.sequence.pop(0)
            if isinstance(item, requests.RequestException):
                raise item
            return item
        if url in self.routes:
            return FakeResponse(200, self.routes[url])
        return FakeResponse(404)
