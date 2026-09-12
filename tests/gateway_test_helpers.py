"""Shared mocks for gateway unit tests (WebReader, FileWriter, SubprocessRunner)."""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock, Mock


def make_fetch_response(content: str = "This is sufficient test content for extraction.") -> MagicMock:
    """Build a requests-style response mock that WebReader.fetch can extract text from."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    html = f"<html><body><p>{content}</p></body></html>"
    mock_response.text = html
    mock_response.content = html.encode("utf-8")
    return mock_response


def make_urlopen_json_response(payload: Dict[str, Any], status: int = 200) -> MagicMock:
    """Build a urllib urlopen context-manager mock returning JSON bytes."""
    body = json.dumps(payload).encode("utf-8")
    mock_response = MagicMock()
    mock_response.getcode.return_value = status
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.read.return_value = body
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)
    return mock_response


def make_urlopen_text_response(text: str, status: int = 200) -> MagicMock:
    """Build a urllib urlopen context-manager mock returning plain text."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = status
    mock_response.headers = {}
    mock_response.read.return_value = text.encode("utf-8")
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)
    return mock_response
