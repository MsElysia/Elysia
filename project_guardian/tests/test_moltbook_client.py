import json

import pytest

from project_guardian.moltbook_client import MoltbookClient, summarize_home, _validate_api_url


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_validate_api_url_requires_www_api_path():
    _validate_api_url("https://www.moltbook.com/api/v1/home")

    with pytest.raises(ValueError):
        _validate_api_url("https://moltbook.com/api/v1/home")

    with pytest.raises(ValueError):
        _validate_api_url("https://www.moltbook.com/login")


def test_summarize_home_handles_moltbook_counts():
    summary = summarize_home(
        {
            "your_account": {"name": "elysiaguardian", "karma": 0, "unread_notification_count": 2},
            "activity_on_your_posts": [{"new_notification_count": "3"}],
            "your_direct_messages": {"pending_request_count": "0", "unread_message_count": "00"},
            "posts_from_accounts_you_follow": {"posts": [{}, {}], "total_following": "2"},
            "latest_moltbook_announcement": {"post_id": "ann-1", "title": "Welcome"},
            "what_to_do_next": ["Read replies", "Browse feed"],
        }
    )

    assert summary["agent_name"] == "elysiaguardian"
    assert summary["unread_notifications"] == 2
    assert summary["new_activity_count"] == 3
    assert summary["dm_unread_messages"] == 0
    assert summary["followed_posts_count"] == 2
    assert summary["what_to_do_next"] == ["Read replies", "Browse feed"]


def test_client_home_check_records_state_without_secret(monkeypatch, tmp_path):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "your_account": {"name": "elysiaguardian", "karma": 1, "unread_notification_count": 0},
                "your_direct_messages": {"pending_request_count": 0, "unread_message_count": 0},
                "posts_from_accounts_you_follow": {"posts": [], "total_following": 0},
                "what_to_do_next": ["Browse the feed"],
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    state_path = tmp_path / "heartbeat-state.json"
    client = MoltbookClient(api_key="moltbook_secret", state_path=state_path, timeout=7)
    result = client.check_home()

    assert captured["url"] == "https://www.moltbook.com/api/v1/home"
    assert captured["auth"] == "Bearer moltbook_secret"
    assert captured["timeout"] == 7
    assert result["summary"]["agent_name"] == "elysiaguardian"
    state_text = state_path.read_text(encoding="utf-8")
    assert "lastMoltbookCheck" in state_text
    assert "moltbook_secret" not in state_text


def test_client_loads_powershell_utf8_bom_credentials(tmp_path):
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text(
        '\ufeff{"api_key": "moltbook_secret", "agent_name": "ElysiaGuardian"}',
        encoding="utf-8",
    )

    client = MoltbookClient(credentials_path=credentials_path, state_path=tmp_path / "state.json")

    assert client.api_key == "moltbook_secret"
    assert client.agent_name == "ElysiaGuardian"
