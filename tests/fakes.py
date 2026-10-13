"""A stand-in for requests.Session that serves canned responses."""

import requests


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", headers: dict | None = None):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", errors="replace")
        self.headers = headers or {}

    def json(self):
        import json

        return json.loads(self.content)


class FakeSession:
    """Serves `sequence` in order first, then `routes` by URL; anything else is a 404."""

    def __init__(self, routes=None, sequence=None):
        self.routes = routes or {}
        self.sequence = list(sequence or [])
        self.urls = []

    def get(self, url, timeout, params=None):
        self.urls.append(url)
        if self.sequence:
            item = self.sequence.pop(0)
            if isinstance(item, requests.RequestException):
                raise item
            return item
        if url in self.routes:
            return FakeResponse(
                200, self.routes[url], {"Last-Modified": "Mon, 12 Oct 2026 00:00:00 GMT"}
            )
        return FakeResponse(404)
