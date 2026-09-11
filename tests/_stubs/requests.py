"""Minimal requests stub for offline GuardianCore import tests."""


class Response:
    status_code = 200
    text = ""
    content = b""

    def json(self):
        return {}

    def raise_for_status(self):
        return None


def get(*_a, **_k):
    return Response()


def post(*_a, **_k):
    return Response()


def request(*_a, **_k):
    return Response()


class Session:
    def __init__(self):
        self.headers = {}

    def get(self, *a, **k):
        return get(*a, **k)

    def post(self, *a, **k):
        return post(*a, **k)

    def request(self, *a, **k):
        return request(*a, **k)


class RequestException(Exception):
    pass


class HTTPError(RequestException):
    pass


class Timeout(RequestException):
    pass


class ConnectionError(RequestException):
    pass


class _Codes:
    ok = 200


codes = _Codes()
