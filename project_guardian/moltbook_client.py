"""Safe Moltbook API client for Elysia.

The API key is only attached to requests targeting
https://www.moltbook.com/api/v1/*.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


API_BASE = "https://www.moltbook.com/api/v1"
ALLOWED_HOST = "www.moltbook.com"
ALLOWED_PATH_PREFIX = "/api/v1/"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS_PATH = Path.home() / ".config" / "moltbook" / "credentials.json"
DEFAULT_STATE_PATH = PROJECT_ROOT / "memory" / "heartbeat-state.json"


class MoltbookAPIError(RuntimeError):
    """Raised when Moltbook returns a non-success response."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _validate_api_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise ValueError(f"Refusing to contact non-Moltbook API endpoint: {url}")
    path = parsed.path or ""
    if path != "/api/v1" and not path.startswith(ALLOWED_PATH_PREFIX):
        raise ValueError(f"Refusing to contact non-API Moltbook endpoint: {url}")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


def _coerce_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _home_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if "your_account" in payload:
        return payload
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def summarize_home(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact, non-secret summary of GET /home."""

    home = _home_payload(payload if isinstance(payload, dict) else {})
    account = home.get("your_account") if isinstance(home.get("your_account"), dict) else {}
    dms = home.get("your_direct_messages") if isinstance(home.get("your_direct_messages"), dict) else {}
    activity = _coerce_list(home.get("activity_on_your_posts"))
    following = home.get("posts_from_accounts_you_follow")
    following = following if isinstance(following, dict) else {}
    announcement = home.get("latest_moltbook_announcement")
    announcement = announcement if isinstance(announcement, dict) else {}

    next_actions = [
        str(item).strip()
        for item in _coerce_list(home.get("what_to_do_next"))
        if str(item).strip()
    ]
    posts = _coerce_list(following.get("posts"))
    new_activity_count = sum(
        _as_int(item.get("new_notification_count"))
        for item in activity
        if isinstance(item, dict)
    )

    return {
        "agent_name": str(account.get("name") or "").strip(),
        "karma": _as_int(account.get("karma")),
        "unread_notifications": _as_int(account.get("unread_notification_count")),
        "activity_on_your_posts_count": len(activity),
        "new_activity_count": new_activity_count,
        "dm_pending_requests": _as_int(dms.get("pending_request_count")),
        "dm_unread_messages": _as_int(dms.get("unread_message_count")),
        "followed_posts_count": len(posts),
        "total_following": _as_int(following.get("total_following")),
        "latest_announcement_title": str(announcement.get("title") or "").strip(),
        "latest_announcement_post_id": str(announcement.get("post_id") or "").strip(),
        "what_to_do_next": next_actions[:5],
    }


class MoltbookClient:
    """Minimal Moltbook client with strict host/path protections."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_base: str = API_BASE,
        credentials_path: Optional[Path | str] = None,
        state_path: Optional[Path | str] = None,
        timeout: float = 30.0,
    ):
        self.api_base = str(api_base).rstrip("/")
        _validate_api_url(self.api_base + "/agents/me")
        self.credentials_path = Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS_PATH
        self.state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
        self.timeout = float(timeout)
        self.agent_name = ""
        self.api_key = api_key or os.environ.get("MOLTBOOK_API_KEY", "").strip()
        if not self.api_key:
            creds = self.load_credentials()
            self.api_key = str(creds.get("api_key") or "").strip()
            self.agent_name = str(creds.get("agent_name") or "").strip()
        if not self.api_key:
            raise MoltbookAPIError(
                f"Moltbook API key not found. Expected MOLTBOOK_API_KEY or {self.credentials_path}"
            )

    def load_credentials(self) -> Dict[str, Any]:
        try:
            return json.loads(self.credentials_path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return {}
        except Exception as exc:
            raise MoltbookAPIError(f"Could not read Moltbook credentials: {exc}") from exc

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        endpoint = path if path.startswith("/") else f"/{path}"
        url = f"{self.api_base}{endpoint}"
        _validate_api_url(url)
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "ElysiaMoltbookClient/1",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8", errors="replace")
            except Exception:
                raw = ""
            raise MoltbookAPIError(
                f"Moltbook API returned HTTP {exc.code}",
                status_code=exc.code,
                body=raw,
            ) from exc
        except urllib.error.URLError as exc:
            raise MoltbookAPIError(f"Moltbook API request failed: {exc.reason}") from exc
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MoltbookAPIError("Moltbook API returned non-JSON response", body=raw[:500]) from exc

    def get_status(self) -> Dict[str, Any]:
        return self._request("GET", "/agents/status")

    def get_me(self) -> Dict[str, Any]:
        return self._request("GET", "/agents/me")

    def get_home(self) -> Dict[str, Any]:
        return self._request("GET", "/home")

    def setup_owner_email(self, email: str) -> Dict[str, Any]:
        return self._request("POST", "/agents/me/setup-owner-email", {"email": email})

    def add_comment(
        self,
        post_id: str,
        content: str,
        *,
        parent_id: str = "",
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"content": str(content or "").strip()}
        if parent_id:
            body["parent_id"] = str(parent_id).strip()
        return self._request("POST", f"/posts/{post_id}/comments", body)

    def create_post(
        self,
        *,
        submolt_name: str,
        title: str,
        content: str = "",
        url: str = "",
        post_type: str = "text",
        tags: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "submolt_name": str(submolt_name or "general").strip(),
            "title": str(title or "").strip(),
            "type": str(post_type or "text").strip(),
        }
        if content:
            body["content"] = str(content).strip()
        if url:
            body["url"] = str(url).strip()
        if tags:
            body["tags"] = [str(t).strip() for t in tags if str(t).strip()][:8]
        return self._request("POST", "/posts", body)

    def load_state(self) -> Dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}

    def save_state(self, state: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")

    def record_home_check(self, summary: Dict[str, Any], *, checked_at: Optional[str] = None) -> Dict[str, Any]:
        now = checked_at or datetime.now(timezone.utc).isoformat()
        state = self.load_state()
        state["lastMoltbookCheck"] = now
        state["moltbook"] = {
            "last_check_at": now,
            "agent_name": summary.get("agent_name") or self.agent_name,
            "karma": summary.get("karma", 0),
            "unread_notifications": summary.get("unread_notifications", 0),
            "dm_unread_messages": summary.get("dm_unread_messages", 0),
            "followed_posts_count": summary.get("followed_posts_count", 0),
            "what_to_do_next": _coerce_list(summary.get("what_to_do_next"))[:5],
        }
        self.save_state(state)
        return state

    def check_home(self, *, update_state: bool = True) -> Dict[str, Any]:
        payload = self.get_home()
        summary = summarize_home(payload)
        state = self.record_home_check(summary) if update_state else self.load_state()
        return {
            "success": True,
            "summary": summary,
            "state_path": str(self.state_path),
            "state_updated": bool(update_state),
            "lastMoltbookCheck": state.get("lastMoltbookCheck"),
        }


def next_actions_text(items: Iterable[Any]) -> str:
    lines = [str(item).strip() for item in items if str(item).strip()]
    return "\n".join(f"- {line}" for line in lines)
