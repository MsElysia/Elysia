# project_guardian/restricted_runtime_adapter.py
# Authenticated in-process API for the existing restricted runtime.
# Persists fact evidence through MemoryCore. Does not open a socket,
# start a second backend, or call model providers.

from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from project_guardian.memory import MemoryCore
from project_guardian.memory_paths import MEMORY_FILEPATH_KEY

API_PREFIX = "/api/restricted/v1"
FACT_CATEGORY = "restricted_fact"
FACT_KIND = "restricted_fact"
FACT_PRIORITY = 0.95
MEMORY_MODULE = "project_guardian.memory.MemoryCore"

_FACT_ID_RE = re.compile(r"^fact_[a-f0-9]{16}$")
_IDENTITY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_STATEMENT_MIN = 12
_STATEMENT_MAX = 2000
_RETRIEVE_MIN_SCORE = 0.5

# Content words only. Retrieval is local overlap, not an embedding model.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "belong",
        "belongs",
        "by",
        "did",
        "do",
        "does",
        "for",
        "from",
        "her",
        "his",
        "how",
        "in",
        "is",
        "it",
        "its",
        "named",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "why",
        "with",
    }
)

# These operations stay refused after a valid identity check.
# The adapter never activates autonomy, submits unrestricted tasks,
# or writes credentials, including when a principal lists them.
HARD_DENY_ROUTES = frozenset(
    {
        ("POST", f"{API_PREFIX}/autonomy/activate"),
        ("POST", f"{API_PREFIX}/tasks/unrestricted"),
        ("POST", f"{API_PREFIX}/credentials"),
        ("PUT", f"{API_PREFIX}/credentials"),
        ("PATCH", f"{API_PREFIX}/credentials"),
    }
)

OPERATOR_FACT_PERMISSIONS = frozenset(
    {
        "facts.save",
        "facts.retrieve",
        "facts.correct",
        "facts.history",
        "runtime.inspect",
    }
)


@dataclass(frozen=True)
class LocalPrincipal:
    """Known local caller. The token is compared in-process and never stored."""

    identity: str
    token: str
    permissions: frozenset


@dataclass(frozen=True)
class AdapterResponse:
    status: int
    body: Dict[str, Any]


def memory_store_identity(memory: MemoryCore) -> Dict[str, str]:
    """Identity of the durable store. Callers must keep this path and module."""
    return {
        "module": MEMORY_MODULE,
        "filepath": os.path.abspath(memory.filepath),
        "canonical_config_key": MEMORY_FILEPATH_KEY,
        "resolver": "project_guardian.memory_paths.resolve_memory_paths",
    }


def _token_matches(presented: str, expected: str) -> bool:
    presented_digest = hashlib.sha256(presented.encode("utf-8")).digest()
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(presented_digest, expected_digest)


def _header_map(headers: Optional[Mapping[str, str]]) -> Dict[str, str]:
    mapped: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        if key is None:
            continue
        mapped[str(key).strip().lower()] = "" if value is None else str(value)
    return mapped


def _content_tokens(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word for word in words if word not in _STOPWORDS and len(word) > 1]


def _clean_statement(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("statement must be a string")
    statement = value.strip()
    if "\x00" in statement:
        raise ValueError("statement contains a null character")
    if len(statement) < _STATEMENT_MIN:
        raise ValueError(f"statement must be at least {_STATEMENT_MIN} characters")
    if len(statement) > _STATEMENT_MAX:
        raise ValueError(f"statement must be at most {_STATEMENT_MAX} characters")
    return statement


class RestrictedRuntimeAdapter:
    """
    Local API adapter over one existing MemoryCore.

    ``handle`` is the contract a later dashboard worker calls. It does not
    bind a port. Pass the runtime's MemoryCore, or the same resolved
    ``memory_filepath`` that runtime already uses.
    """

    def __init__(
        self,
        principals: Sequence[LocalPrincipal],
        memory: Optional[MemoryCore] = None,
        memory_filepath: Optional[str] = None,
    ) -> None:
        if memory is None and not memory_filepath:
            raise ValueError("memory or memory_filepath is required")
        if not principals:
            raise ValueError("at least one local principal is required")
        seen = set()
        normalized: Dict[str, LocalPrincipal] = {}
        for principal in principals:
            identity = principal.identity.strip()
            if not _IDENTITY_RE.match(identity):
                raise ValueError(f"invalid principal identity: {principal.identity!r}")
            if not principal.token:
                raise ValueError(f"principal {identity} is missing a token")
            if identity in seen:
                raise ValueError(f"duplicate principal identity: {identity}")
            seen.add(identity)
            normalized[identity] = LocalPrincipal(
                identity=identity,
                token=principal.token,
                permissions=frozenset(principal.permissions),
            )
        self._principals = normalized
        self._lock = threading.Lock()
        if memory is not None:
            self.memory = memory
        else:
            self.memory = MemoryCore(
                filepath=str(memory_filepath),
                timeline_memory=None,
                enable_timeline_logging=False,
                enable_vector_search=False,
            )

    def store_identity(self) -> Dict[str, str]:
        return memory_store_identity(self.memory)

    def handle(
        self,
        method: str,
        path: str,
        headers: Optional[Mapping[str, str]] = None,
        body: Optional[Mapping[str, Any]] = None,
    ) -> AdapterResponse:
        verb = (method or "").strip().upper()
        route = (path or "").strip()
        if not verb or not route.startswith(API_PREFIX):
            return _error(404, "not_found", "unknown route")
        if "?" in route or route != route.rstrip("/") or "\\" in route:
            return _error(400, "invalid_request", "path must be a canonical route without a query")
        if body is not None and not isinstance(body, Mapping):
            return _error(400, "invalid_request", "body must be an object")

        principal, auth_error = self._authenticate(_header_map(headers))
        if auth_error is not None:
            return auth_error
        assert principal is not None

        if (verb, route) in HARD_DENY_ROUTES:
            return _error(403, "forbidden", "operation is not available on the restricted runtime")

        payload = dict(body or {})
        if verb == "POST" and route == f"{API_PREFIX}/facts":
            return self._require(principal, "facts.save") or self._save_fact(principal, payload)
        if verb == "POST" and route == f"{API_PREFIX}/facts/retrieve":
            return self._require(principal, "facts.retrieve") or self._retrieve_facts(payload)
        if verb == "GET" and route == f"{API_PREFIX}/memory-store":
            return self._require(principal, "runtime.inspect") or AdapterResponse(
                200, {"ok": True, "memory_store": self.store_identity()}
            )

        correction = _FACT_CORRECTION_RE.match(route)
        if verb == "POST" and correction:
            return self._require(principal, "facts.correct") or self._correct_fact(
                principal, correction.group(1), payload
            )
        history = _FACT_HISTORY_RE.match(route)
        if verb == "GET" and history:
            return self._require(principal, "facts.history") or self._fact_history(history.group(1))
        return _error(404, "not_found", "unknown route")

    def _authenticate(
        self, headers: Mapping[str, str]
    ) -> Tuple[Optional[LocalPrincipal], Optional[AdapterResponse]]:
        identity = headers.get("x-elysia-identity", "").strip()
        presented = headers.get("x-elysia-token", "")
        principal = self._principals.get(identity)
        expected = principal.token if principal is not None else ""
        if principal is None or not _token_matches(presented, expected):
            return None, _error(401, "unauthorized", "identity or token was rejected")
        return principal, None

    def _require(self, principal: LocalPrincipal, permission: str) -> Optional[AdapterResponse]:
        if permission not in principal.permissions:
            return _error(403, "forbidden", f"missing permission {permission}")
        return None

    def _save_fact(self, principal: LocalPrincipal, body: Mapping[str, Any]) -> AdapterResponse:
        try:
            statement = _clean_statement(body.get("statement"))
        except ValueError as exc:
            return _error(400, "invalid_request", str(exc))
        fact_id = "fact_" + uuid.uuid4().hex[:16]
        record = self._append_event(
            fact_id=fact_id,
            revision=1,
            statement=statement,
            operation="save",
            actor=principal.identity,
            previous_statement=None,
        )
        return AdapterResponse(
            201,
            {
                "ok": True,
                "operation": "facts.save",
                "fact": _public_fact(record, current=True),
                "memory_store": self.store_identity(),
            },
        )

    def _correct_fact(
        self, principal: LocalPrincipal, fact_id: str, body: Mapping[str, Any]
    ) -> AdapterResponse:
        if not _FACT_ID_RE.match(fact_id):
            return _error(404, "not_found", "fact not found")
        try:
            statement = _clean_statement(body.get("statement"))
        except ValueError as exc:
            return _error(400, "invalid_request", str(exc))
        with self._lock:
            revisions = self._revisions_for(fact_id)
            if not revisions:
                return _error(404, "not_found", "fact not found")
            current = revisions[-1]
            if statement == current["statement"]:
                return _error(400, "invalid_request", "statement is unchanged")
            record = self._append_event(
                fact_id=fact_id,
                revision=int(current["revision"]) + 1,
                statement=statement,
                operation="correct",
                actor=principal.identity,
                previous_statement=current["statement"],
                hold_lock=True,
            )
        return AdapterResponse(
            200,
            {
                "ok": True,
                "operation": "facts.correct",
                "fact": _public_fact(record, current=True),
                "memory_store": self.store_identity(),
            },
        )

    def _retrieve_facts(self, body: Mapping[str, Any]) -> AdapterResponse:
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            return _error(400, "invalid_request", "query must be a non-empty string")
        query_tokens = _content_tokens(query)
        if not query_tokens:
            return _error(400, "invalid_request", "query has no content words")
        query_set = set(query_tokens)
        matches: List[Dict[str, Any]] = []
        with self._lock:
            for fact in self._current_facts():
                fact_tokens = _content_tokens(fact["statement"])
                if not fact_tokens:
                    continue
                overlap = query_set.intersection(fact_tokens)
                score = len(overlap) / len(query_set)
                if not overlap or score < _RETRIEVE_MIN_SCORE:
                    continue
                public = _public_fact(fact, current=True)
                public["score"] = round(score, 6)
                public["matched_tokens"] = sorted(overlap)
                matches.append(public)
        matches.sort(key=lambda item: (-item["score"], item["fact_id"]))
        return AdapterResponse(
            200,
            {
                "ok": True,
                "operation": "facts.retrieve",
                "query": query.strip(),
                "matches": matches,
                "memory_store": self.store_identity(),
            },
        )

    def _fact_history(self, fact_id: str) -> AdapterResponse:
        if not _FACT_ID_RE.match(fact_id):
            return _error(404, "not_found", "fact not found")
        with self._lock:
            revisions = self._revisions_for(fact_id)
        if not revisions:
            return _error(404, "not_found", "fact not found")
        latest = revisions[-1]["revision"]
        return AdapterResponse(
            200,
            {
                "ok": True,
                "operation": "facts.history",
                "fact_id": fact_id,
                "revisions": [
                    _public_fact(item, current=item["revision"] == latest) for item in revisions
                ],
                "memory_store": self.store_identity(),
            },
        )

    def _current_facts(self) -> List[Dict[str, Any]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        for record in self._fact_records():
            previous = by_id.get(record["fact_id"])
            if previous is None or record["revision"] >= previous["revision"]:
                by_id[record["fact_id"]] = record
        return list(by_id.values())

    def _revisions_for(self, fact_id: str) -> List[Dict[str, Any]]:
        rows = [record for record in self._fact_records() if record["fact_id"] == fact_id]
        rows.sort(key=lambda item: (item["revision"], item["time"]))
        return rows

    def _fact_records(self) -> List[Dict[str, Any]]:
        self.memory.load_if_needed()
        records: List[Dict[str, Any]] = []
        for entry in self.memory.memory_log:
            if not isinstance(entry, dict):
                continue
            metadata = entry.get("metadata") or {}
            if not isinstance(metadata, dict) or metadata.get("kind") != FACT_KIND:
                continue
            fact_id = metadata.get("fact_id")
            if not isinstance(fact_id, str) or not _FACT_ID_RE.match(fact_id):
                continue
            try:
                revision = int(metadata.get("revision"))
            except (TypeError, ValueError):
                continue
            statement = metadata.get("statement")
            if not isinstance(statement, str):
                continue
            records.append(
                {
                    "fact_id": fact_id,
                    "revision": revision,
                    "statement": statement,
                    "operation": metadata.get("operation") or "save",
                    "actor": metadata.get("actor") or "",
                    "previous_statement": metadata.get("previous_statement"),
                    "time": entry.get("time") or "",
                }
            )
        return records

    def _append_event(
        self,
        *,
        fact_id: str,
        revision: int,
        statement: str,
        operation: str,
        actor: str,
        previous_statement: Optional[str],
        hold_lock: bool = False,
    ) -> Dict[str, Any]:
        metadata = {
            "kind": FACT_KIND,
            "fact_id": fact_id,
            "revision": revision,
            "statement": statement,
            "operation": operation,
            "actor": actor,
            "previous_statement": previous_statement,
        }
        thought = f"Restricted fact {fact_id} revision {revision}: {statement}"
        entry = {
            "fact_id": fact_id,
            "revision": revision,
            "statement": statement,
            "operation": operation,
            "actor": actor,
            "previous_statement": previous_statement,
        }

        def write() -> None:
            before = len(self.memory.memory_log)
            self.memory.remember(
                thought=thought,
                category=FACT_CATEGORY,
                priority=FACT_PRIORITY,
                metadata=metadata,
            )
            if not _log_has_revision(self.memory, fact_id, revision):
                # remember() can drop a write under startup filters. Keep the
                # same MemoryCore file rather than opening another store.
                self.memory.load_if_needed()
                if len(self.memory.memory_log) == before:
                    self.memory.memory_log.append(
                        {
                            "time": _now_iso(),
                            "thought": thought,
                            "category": FACT_CATEGORY,
                            "priority": FACT_PRIORITY,
                            "metadata": metadata,
                        }
                    )
                    self.memory._save()

        if hold_lock:
            write()
        else:
            with self._lock:
                write()
        return entry


_FACT_CORRECTION_RE = re.compile(
    rf"^{re.escape(API_PREFIX)}/facts/(fact_[a-f0-9]{{16}})/corrections$"
)
_FACT_HISTORY_RE = re.compile(
    rf"^{re.escape(API_PREFIX)}/facts/(fact_[a-f0-9]{{16}})/history$"
)


def _log_has_revision(memory: MemoryCore, fact_id: str, revision: int) -> bool:
    for entry in memory.memory_log:
        metadata = entry.get("metadata") if isinstance(entry, dict) else None
        if not isinstance(metadata, dict):
            continue
        if metadata.get("fact_id") == fact_id and metadata.get("revision") == revision:
            return True
    return False


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now().isoformat()


def _public_fact(record: Mapping[str, Any], *, current: bool) -> Dict[str, Any]:
    return {
        "fact_id": record["fact_id"],
        "revision": record["revision"],
        "statement": record["statement"],
        "operation": record["operation"],
        "actor": record["actor"],
        "previous_statement": record["previous_statement"],
        "current": current,
    }


def _error(status: int, code: str, detail: str) -> AdapterResponse:
    return AdapterResponse(status, {"ok": False, "error": code, "detail": detail})
